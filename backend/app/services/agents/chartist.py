import logging
import re
from typing import Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
    HINT_STYLES,
    ContractViolation,
    chart_type_hint,
    render_spec,
    validate_chart_code,
)

logger = logging.getLogger(__name__)

# The planner sources whose chart type counts as a decision. "default" -- the
# bare "bar" used when neither the model nor a keyword decided -- does not, and
# neither does a plan that records no source at all.
_CHOSEN_BY = ("llm", "keywords")

# Stamped onto deterministically generated code. Without it a fallback chart is
# indistinguishable from a model-written one in the response, and a smoke test
# that only asks "did a figure render" reports success when the model failed.
FALLBACK_MARKER = "# promptdash: deterministic fallback (model output unusable)"

# A thinking model (Qwen3.5) returns "\n</think>\n\n" before its code, because
# generation begins after "<think>\n". _strip_prose_prefix happens to drop it
# today, but only because "</think>" fails the looks-like-code test -- if the
# model ever emits real reasoning whose lines look like code, that breaks. Strip
# it explicitly instead of relying on an accident.
THINK_PREFIX = re.compile(r"^.*?</think>\s*", re.DOTALL)

class ChartistAgent:
    """
    Agent responsible for generating Python code to visualize data.
    """
    
    def __init__(self, llm, generator=None, chart_type_hint_style: str | None = None):
        """`generator` replaces only the text-generation step.

        Anything with `.invoke(variables) -> str` can stand in for the chain,
        which is how a different model is compared on this harness: the prompt,
        the sanitiser, the contract and the fallback below are shared, so the
        model is the only thing that differs.

        `chart_type_hint_style` overrides `CHARTIST_CHART_TYPE_HINT` for this
        agent, so one process can run both sides of that A/B at once. None means
        take the setting.
        """
        self.llm = llm
        self.generator = generator
        if chart_type_hint_style is None:
            from app.core.config import get_settings

            chart_type_hint_style = get_settings().CHARTIST_CHART_TYPE_HINT
        self.chart_type_hint_style = (chart_type_hint_style or "off").strip().lower()
        if self.chart_type_hint_style not in HINT_STYLES:
            # Fail loudly, as llm.py does for LLM_BACKEND. Otherwise a typo such
            # as "on" switches the hint off with no sign that anything is wrong.
            raise ValueError(
                f"CHARTIST_CHART_TYPE_HINT must be one of {HINT_STYLES}, "
                f"got {chart_type_hint_style!r}"
            )
        # Why the last generation fell back, if it did. Without this the
        # fallback's own (valid) code is all anyone can inspect afterwards,
        # and the reason the model's answer was rejected is gone.
        self.last_violations: list[str] = []

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", CHARTIST_SYSTEM_PROMPT),
            ("human", CHARTIST_USER_TEMPLATE),
        ])

        self.chain = None if llm is None else self.prompt | self.llm | StrOutputParser()

    def _extract_code_block(self, raw: str) -> str:
        if not raw:
            return ""
        if "</think>" in raw:
            raw = THINK_PREFIX.sub("", raw, count=1)
        fenced = re.findall(r"```(?:python)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            return fenced[0].strip()
        return raw.strip()

    def _is_likely_code_line(self, line: str) -> bool:
        line = line.strip()
        return bool(
            re.match(
                r"^(import |from |df\[|fig\s*=|#|[A-Za-z_]\w*\s*=|if |for |while |try:|except |print\()",
                line,
            )
        )

    def _strip_prose_prefix(self, code: str) -> str:
        lines = code.splitlines()
        start_idx = 0
        for idx, line in enumerate(lines):
            if self._is_likely_code_line(line):
                start_idx = idx
                break
        return "\n".join(lines[start_idx:]).strip()

    def _fallback_plotly_code(self, data_context: Dict[str, Any], viz_type: str) -> str:
        columns = data_context.get("columns", []) or []
        dtypes = data_context.get("dtypes", {}) or {}
        numeric_cols = [c for c in columns if "int" in str(dtypes.get(c, "")).lower() or "float" in str(dtypes.get(c, "")).lower()]
        datetime_cols = [c for c in columns if "date" in c.lower() or "datetime" in str(dtypes.get(c, "")).lower()]

        x_col = datetime_cols[0] if datetime_cols else (columns[0] if columns else None)
        y_col = numeric_cols[0] if numeric_cols else (columns[1] if len(columns) > 1 else None)
        color_col = None
        for c in columns:
            if c not in {x_col, y_col} and "category" in c.lower():
                color_col = c
                break

        if not x_col or not y_col:
            return (
                f"{FALLBACK_MARKER}\n"
                "import plotly.express as px\n"
                "fig = px.histogram(df)\n"
                "print(fig.to_json())"
            )

        if viz_type == "line":
            plot_call = f"px.line(df, x='{x_col}', y='{y_col}'" + (f", color='{color_col}'" if color_col else "") + ")"
        elif viz_type == "scatter":
            plot_call = f"px.scatter(df, x='{x_col}', y='{y_col}'" + (f", color='{color_col}'" if color_col else "") + ")"
        else:
            plot_call = f"px.bar(df, x='{x_col}', y='{y_col}'" + (f", color='{color_col}'" if color_col else "") + ")"

        return (
            f"{FALLBACK_MARKER}\n"
            "import plotly.express as px\n"
            f"fig = {plot_call}\n"
            "print(fig.to_json())"
        )

    # Property names the model reliably gets wrong, mapped to the real ones.
    # Measured, not guessed: `valueprefix` lost two of six blocks in a dashboard
    # build, because Plotly's indicator number takes `prefix`/`suffix`. Keeping
    # the list to names that cannot mean anything else keeps this a repair
    # rather than a rewrite — anything subtler stays a contract violation and
    # falls back, as before.
    _PROPERTY_FIXES: tuple[tuple[str, str], ...] = (
        ("valueprefix", "prefix"),
        ("valuesuffix", "suffix"),
        ("valueformat_", "valueformat"),
    )

    def _repair_properties(self, code: str) -> str:
        for wrong, right in self._PROPERTY_FIXES:
            code = re.sub(rf"(?<![A-Za-z_]){wrong}(?![A-Za-z_])", right, code)
        return code

    def _sanitize_generated_code(self, raw: str, data_context: Dict[str, Any], viz_type: str) -> str:
        code = self._extract_code_block(raw)
        code = code.replace("“", "\"").replace("”", "\"").replace("’", "'").replace("‘", "'")
        code = self._strip_prose_prefix(code)
        code = self._repair_properties(code)

        violations = validate_chart_code(code)
        if ContractViolation.NO_JSON_PRINT in violations and "fig =" in code:
            code = f"{code}\nprint(fig.to_json())"
            violations = validate_chart_code(code)
        self.last_violations = [v.value for v in violations]
        if violations:
            logger.warning("[chartist] contract violations %s, using fallback", violations)
            return self._fallback_plotly_code(data_context, viz_type)
        return code

    def _task_description(
        self,
        user_query: str,
        task_plan: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]],
    ) -> str:
        """The `Task:` line of the prompt — the user's own question.

        This used to synthesise metadata instead:

            "Build a bar chart. Style: {'theme': 'plotly_white'}.
             Prefer these columns: [...]. Suggested encoding: ..."

        The fine-tuned chartist was trained on 1,926 rows whose Task line was a
        natural dashboard question ("Monthly MRR trend for the whole business"),
        paired with the same schema block that follows it. Replacing the question
        with generated prose puts the prompt out of distribution and throws away
        the only signal the model was taught to read.

        What that argument does NOT establish is that a *short* chart-type hint
        hurts. It is one clause, not a paragraph of metadata, and whether a 9B
        model follows it is a question for the eval rather than for a docstring.
        `CHARTIST_CHART_TYPE_HINT` wires the planner's decision through, in the
        exact wording `chart_type_hint` produces, so the training exporter and
        the live call cannot drift. It defaults to "off": measured on the frozen
        300 by `chartist-finetune/ab_planner_hint.py`, which is the only thing
        that should ever move that default.

        Two guards keep a hint from doing harm. It is sent only when the
        planner's label was a decision -- the model's, or a keyword match --
        never the bare "bar" it falls back to when nothing decided. And it is
        never sent when the question already names its chart, which is every
        question the dashboard architect writes ("... as a line chart"); there a
        second instruction is redundant at best and, after a planner fallback,
        contradicts the first.

        The other hint is explicitly-unavailable fields. Note that this one is
        also out of distribution — the phrase appears in 0 of 1,929 training
        rows, despite `missing_field` being an oversampled hard case — so it is
        a candidate for the same treatment and the same measurement.
        """
        task = (user_query or "").strip() or str(task_plan.get("data_requirements", "")).strip()
        # Before the missing-fields note, so the hint sits against the question
        # exactly as the A/B harness placed it.
        if task_plan.get("chart_type_source") in _CHOSEN_BY:
            task = chart_type_hint(
                task,
                str(task_plan.get("visualization_type", "")),
                self.chart_type_hint_style,
            )
        plan = dataframe_plan or {}
        missing = plan.get("missing_fields") or []
        if missing:
            task = f"{task}\n\nNot available in this data, do not use: {list(missing)}"
        return task

    def generate_code(
        self,
        user_query: str,
        task_plan: Dict[str, Any],
        data_context: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generates Plotly code for the user's question against this schema.

        With a `spec` (a chart plan from the dashboard planner) the task text is
        the plan itself; the question-only path is unchanged for single blocks.
        """
        viz_type = task_plan.get("visualization_type", "bar")
        try:
            source = self.generator or self.chain
            if source is None:
                raise RuntimeError("chartist has neither a model nor a generator")
            task = (
                render_spec(spec)
                if spec
                else self._task_description(user_query, task_plan, dataframe_plan)
            )
            raw = source.invoke({
                "task": task,
                "columns": str(data_context.get("columns", [])),
                "dtypes": str(data_context.get("dtypes", {})),
                "sample_rows": str(data_context.get("sample", [])),
            })
            return self._sanitize_generated_code(raw, data_context, viz_type)
        except Exception:
            logger.exception("[chartist] generation failed, using deterministic fallback")
            return self._fallback_plotly_code(data_context, viz_type)

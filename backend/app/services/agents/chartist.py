import logging
import re
from typing import Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.agents.chartist_contract import (
    CHARTIST_SYSTEM_PROMPT,
    CHARTIST_USER_TEMPLATE,
    ContractViolation,
    validate_chart_code,
)

logger = logging.getLogger(__name__)

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
    
    def __init__(self, llm):
        self.llm = llm
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", CHARTIST_SYSTEM_PROMPT),
            ("human", CHARTIST_USER_TEMPLATE),
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()

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
        the only signal the model was taught to read. The chart type is inferred
        from the question, exactly as in training, which is also why the planner
        no longer needs to steer it.

        The one hint kept is explicitly-unavailable fields, because `missing_field`
        was an oversampled hard case in training and the note is short.
        """
        task = (user_query or "").strip() or str(task_plan.get("data_requirements", "")).strip()
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
    ) -> str:
        """
        Generates Plotly code for the user's question against this schema.
        """
        viz_type = task_plan.get("visualization_type", "bar")
        try:
            raw = self.chain.invoke({
                "task": self._task_description(user_query, task_plan, dataframe_plan),
                "columns": str(data_context.get("columns", [])),
                "dtypes": str(data_context.get("dtypes", {})),
                "sample_rows": str(data_context.get("sample", [])),
            })
            return self._sanitize_generated_code(raw, data_context, viz_type)
        except Exception:
            logger.exception("[chartist] generation failed, using deterministic fallback")
            return self._fallback_plotly_code(data_context, viz_type)

import logging
import re
from typing import Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.services.agents.chartist_contract import (
    AGG_RULE_MODES,
    CHARTIST_REPAIR_TEMPLATE,
    CHARTIST_USER_TEMPLATE,
    HINT_STYLES,
    chart_type_hint,
    chartist_system_prompt,
    render_spec,
)

logger = logging.getLogger(__name__)

# The planner sources whose chart type counts as a decision. "default" -- the
# bare "bar" used when neither the model nor a keyword decided -- does not, and
# neither does a plan that records no source at all.
_CHOSEN_BY = ("llm", "keywords")


class ChartistUnavailable(RuntimeError):
    """The model could not be asked: none is configured, or the call itself failed.

    Raised, never papered over. A chart the model did not write is not shown:
    there is no hardcoded stand-in, so the caller reports the failure instead.
    """

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
    
    def __init__(
        self,
        llm,
        generator=None,
        chart_type_hint_style: str | None = None,
        agg_rule: str | None = None,
    ):
        """`generator` replaces only the text-generation step.

        Anything with `.invoke(variables) -> str` can stand in for the chain,
        which is how a different model is compared on this harness: the prompt,
        the reply reading, the contract and the repair turn are shared, so the
        model is the only thing that differs. A repair request carries two more
        variables, `previous_code` and `problem`, and every request carries
        `system`, the system text this agent sends.

        `chart_type_hint_style` overrides `CHARTIST_CHART_TYPE_HINT` and
        `agg_rule` overrides `CHARTIST_AGG_RULE` for this agent, so one process
        can run both sides of either A/B at once. None means take the setting.
        """
        self.llm = llm
        self.generator = generator
        if chart_type_hint_style is None or agg_rule is None:
            from app.core.config import get_settings

            settings = get_settings()
            if chart_type_hint_style is None:
                chart_type_hint_style = settings.CHARTIST_CHART_TYPE_HINT
            if agg_rule is None:
                agg_rule = settings.CHARTIST_AGG_RULE
        self.agg_rule = (agg_rule or "off").strip().lower()
        if self.agg_rule not in AGG_RULE_MODES:
            raise ValueError(f"CHARTIST_AGG_RULE must be one of {AGG_RULE_MODES}, got {agg_rule!r}")
        # The first call, the repair turn and a stand-in generator all send this text.
        self.system_prompt = chartist_system_prompt(self.agg_rule)
        self.chart_type_hint_style = (chart_type_hint_style or "off").strip().lower()
        if self.chart_type_hint_style not in HINT_STYLES:
            # Fail loudly, as llm.py does for LLM_BACKEND. Otherwise a typo such
            # as "on" switches the hint off with no sign that anything is wrong.
            raise ValueError(
                f"CHARTIST_CHART_TYPE_HINT must be one of {HINT_STYLES}, "
                f"got {chart_type_hint_style!r}"
            )
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", CHARTIST_USER_TEMPLATE),
        ])
        # The same conversation, continued: the model's own code as its answer,
        # then what went wrong with it. The code goes in as a variable's value,
        # so its braces are never read as template fields.
        self.repair_prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", CHARTIST_USER_TEMPLATE),
            ("ai", "{previous_code}"),
            ("human", CHARTIST_REPAIR_TEMPLATE),
        ])

        self.chain = None if llm is None else self.prompt | self.llm | StrOutputParser()
        self.repair_chain = None if llm is None else self.repair_prompt | self.llm | StrOutputParser()

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

    def _read_code(self, raw: str) -> str:
        """The code in the model's reply, as written: fences, a think prefix,
        curly quotes and leading prose are removed, and nothing else is touched.
        Whether it is any good is for the contract and the run to say."""
        code = self._extract_code_block(raw)
        code = code.replace("“", "\"").replace("”", "\"").replace("’", "'").replace("‘", "'")
        return self._strip_prose_prefix(code)

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

    def prompt_variables(
        self,
        user_query: str,
        task_plan: Dict[str, Any],
        data_context: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """What the model is asked, kept so a repair continues the same conversation.

        With a `spec` (a chart plan from the dashboard planner) the task text is
        the plan itself; the question-only path is unchanged for single blocks.
        """
        task = (
            render_spec(spec)
            if spec
            else self._task_description(user_query, task_plan, dataframe_plan)
        )
        return {
            "task": task,
            "columns": str(data_context.get("columns", [])),
            "dtypes": str(data_context.get("dtypes", {})),
            "sample_rows": str(data_context.get("sample", [])),
        }

    def write(self, variables: Dict[str, str], previous_code: str = "", problem: str = "") -> str:
        """One model call: chart code for `variables`, or, given its `previous_code`
        and what went wrong with it, the model's own fix. Raises ChartistUnavailable."""
        repairing = bool(previous_code)
        if self.generator is not None:
            source = self.generator
        else:
            source = self.repair_chain if repairing else self.chain
        if source is None:
            raise ChartistUnavailable("the chartist has neither a model nor a generator")
        payload = {**variables, "previous_code": previous_code, "problem": problem} if repairing else variables
        if self.generator is not None:
            payload = {**payload, "system": self.system_prompt}
        try:
            raw = source.invoke(payload)
        except Exception as exc:  # noqa: BLE001 - reported to the caller, never replaced
            logger.warning("[chartist] the model call failed: %s", exc)
            raise ChartistUnavailable(str(exc) or type(exc).__name__) from exc
        return self._read_code(raw)

    def generate_code(
        self,
        user_query: str,
        task_plan: Dict[str, Any],
        data_context: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]] = None,
        spec: Optional[Dict[str, Any]] = None,
    ) -> str:
        """The model's Plotly code for the user's question against this schema."""
        return self.write(self.prompt_variables(user_query, task_plan, data_context, dataframe_plan, spec))

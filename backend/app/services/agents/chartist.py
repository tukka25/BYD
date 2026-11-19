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
            "import plotly.express as px\n"
            f"fig = {plot_call}\n"
            "print(fig.to_json())"
        )

    def _sanitize_generated_code(self, raw: str, data_context: Dict[str, Any], viz_type: str) -> str:
        code = self._extract_code_block(raw)
        code = code.replace("“", "\"").replace("”", "\"").replace("’", "'").replace("‘", "'")
        code = self._strip_prose_prefix(code)

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
        task_plan: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]],
    ) -> str:
        parts = [
            f"Build a {task_plan.get('visualization_type', 'bar')} chart.",
            f"Style: {task_plan.get('style_config', {})}.",
        ]
        plan = dataframe_plan or {}
        if plan.get("selected_columns"):
            parts.append(f"Prefer these columns: {plan['selected_columns']}.")
        if plan.get("plotly_ready_spec"):
            parts.append(f"Suggested encoding: {plan['plotly_ready_spec']}.")
        if plan.get("missing_fields"):
            parts.append(f"Unavailable, do not use: {plan['missing_fields']}.")
        return " ".join(parts)

    def generate_code(
        self,
        task_plan: Dict[str, Any],
        data_context: Dict[str, Any],
        dataframe_plan: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generates Python code based on the plan and data schema.
        """
        viz_type = task_plan.get("visualization_type", "bar")
        try:
            raw = self.chain.invoke({
                "task": self._task_description(task_plan, dataframe_plan),
                "columns": str(data_context.get("columns", [])),
                "dtypes": str(data_context.get("dtypes", {})),
                "sample_rows": str(data_context.get("sample", [])),
            })
            return self._sanitize_generated_code(raw, data_context, viz_type)
        except Exception as e:
            return self._fallback_plotly_code(data_context, viz_type)

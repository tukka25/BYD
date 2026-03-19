import ast
import re
from typing import Dict, Any, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

class ChartistAgent:
    """
    Agent responsible for generating Python code to visualize data.
    """
    
    def __init__(self, llm):
        self.llm = llm
        
        # System prompt focused on Plotly JSON output
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an expert Data Visualization Engineer specializing in Plotly.
            
            Your task is to write a Python script that:
            1. Accepts a pandas DataFrame named `df` (assume it's already loaded with the provided schema).
            2. Creates a Plotly figure using `plotly.express` (preferred) or `plotly.graph_objects`.
            3. Applies the requested style and configuration.
            4. VERY IMPORTANT: The script must end by printing the figure as a JSON string using `print(fig.to_json())`.
            5. Respect dataframe planning hints when provided:
               - prefer selected_columns from dataframe_plan
               - use plotly_ready_spec fields (x/y/color/group_by/aggregation/chart_hint) if available
               - avoid using missing_fields
            
            Do NOT include code to read the file (e.g. pd.read_csv). Assume `df` is available in the global scope.
            Do NOT show the plot (fig.show()).
            Do NOT save the plot to a file.
            NEVER include explanations, markdown, bullet points, or natural language text.
            Output executable Python only.
            
            Only output the Python code block. Do not include markdown formatting like ```python.
            """),
            ("human", """
            Task: {task_description}
            Visualization Type: {viz_type}
            Style Config: {style_config}
            Dataframe Plan: {dataframe_plan}
            Data Schema:
            Columns: {columns}
            Sample Data: {sample_data}
            
            Generate the Python code now.
            """)
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

        # Reject non-Plotly/matplotlib style outputs and fallback.
        lowered = code.lower()
        if "matplotlib" in lowered or "plt." in lowered or "fig.show(" in lowered:
            return self._fallback_plotly_code(data_context, viz_type)

        if "print(fig.to_json())" not in code:
            if "fig =" in code:
                code = f"{code}\nprint(fig.to_json())"
            else:
                return self._fallback_plotly_code(data_context, viz_type)

        try:
            ast.parse(code)
            return code
        except SyntaxError:
            return self._fallback_plotly_code(data_context, viz_type)

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
                "task_description": "Generate a chart based on user request",
                "viz_type": viz_type,
                "style_config": str(task_plan.get("style_config", {})),
                "dataframe_plan": str(dataframe_plan or {}),
                "columns": str(data_context.get("columns", [])),
                "sample_data": str(data_context.get("sample", []))
            })
            return self._sanitize_generated_code(raw, data_context, viz_type)
        except Exception as e:
            return self._fallback_plotly_code(data_context, viz_type)

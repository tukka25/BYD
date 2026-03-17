from typing import Dict, Any, List, Optional
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
            
            Do NOT include code to read the file (e.g. pd.read_csv). Assume `df` is available in the global scope.
            Do NOT show the plot (fig.show()).
            Do NOT save the plot to a file.
            
            Only output the Python code block. Do not include markdown formatting like ```python.
            """),
            ("human", """
            Task: {task_description}
            Visualization Type: {viz_type}
            Style Config: {style_config}
            Data Schema:
            Columns: {columns}
            Sample Data: {sample_data}
            
            Generate the Python code now.
            """)
        ])
        
        self.chain = self.prompt | self.llm | StrOutputParser()

    def generate_code(self, task_plan: Dict[str, Any], data_context: Dict[str, Any]) -> str:
        """
        Generates Python code based on the plan and data schema.
        """
        try:
            return self.chain.invoke({
                "task_description": "Generate a chart based on user request",
                "viz_type": task_plan.get("visualization_type", "bar"),
                "style_config": str(task_plan.get("style_config", {})),
                "columns": str(data_context.get("columns", [])),
                "sample_data": str(data_context.get("sample", []))
            })
        except Exception as e:
            return f"# Error generating code: {str(e)}"

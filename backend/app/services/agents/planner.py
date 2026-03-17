from typing import Dict, Any, List, Optional
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

class TaskPlan(BaseModel):
    steps: List[str] = Field(description="List of steps to execute the task")
    visualization_type: str = Field(description="Type of chart to generate (e.g., 'bar', 'line', 'scatter')")
    style_config: Dict[str, Any] = Field(description="Style configuration for the chart")
    data_requirements: str = Field(description="Description of data needed")

class PlannerAgent:
    """
    Agent responsible for interpreting user intent and creating a task plan.
    """
    
    def __init__(self, llm):
        self.llm = llm
        self.parser = JsonOutputParser(pydantic_object=TaskPlan)
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", """
            You are an expert Data Visualization Planner. Your goal is to break down a user's request into actionable steps.
            
            Based on the user's request:
            1. Determine the best type of visualization (bar, line, scatter, pie, heatmap, etc.).
            2. Define a color palette suitable for a professional dashboard (prefer 'plotly_dark' or 'seaborn' themes if not specified).
            3. List the logical steps required to process data and generate the graph.
            4. Identify what kind of data is needed (e.g., "sales data with dates").
            
            Return the output strictly in JSON format matching the TaskPlan schema.
            """),
            ("human", "{input}")
        ])
        
        self.chain = self.prompt | self.llm | self.parser

    def create_plan(self, user_query: str) -> TaskPlan:
        """
        Generates a plan based on the user query.
        """
        try:
            return self.chain.invoke({"input": user_query})
        except Exception as e:
            # Fallback for mock LLM or parsing errors
            print(f"Planning Error: {e}")
            return {
                "steps": ["Find relevant data", "Generate chart"],
                "visualization_type": "bar",
                "style_config": {"theme": "plotly_white"},
                "data_requirements": "general data"
            }

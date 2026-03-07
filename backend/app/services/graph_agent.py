from typing import TypedDict, Annotated, Sequence, Any
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
import pandas as pd
import io
import base64
import matplotlib.pyplot as plt
import sys
from io import StringIO

# Define the state
class AgentState(TypedDict):
    messages: Sequence[BaseMessage]
    code: str
    output: str
    error: str

def generate_code_node(state: AgentState):
    """
    Generates Python code to create a graph based on the user's request.
    This function simulates an SLM (Small Language Model) response.
    """
    messages = state['messages']
    last_message = messages[-1].content
    
    # In a real implementation, we would call a local SLM here, e.g., using Ollama
    # from langchain_community.llms import Ollama
    # llm = Ollama(model="qwen:3b-8b")
    # response = llm.invoke(f"Write python code to generate a graph for: {last_message}...")
    
    # Mock logic for demonstration purposes
    code_template = """
import matplotlib.pyplot as plt
import io
import base64
import numpy as np

# Generate dummy data relevant to the request
categories = ['A', 'B', 'C', 'D', 'E']
values = np.random.randint(10, 100, size=5)

plt.figure(figsize=(10, 6))
plt.bar(categories, values, color='skyblue')
plt.title(f'Generated Graph for: {title}')
plt.xlabel('Category')
plt.ylabel('Value')
plt.grid(axis='y', linestyle='--', alpha=0.7)

# Save to base64
buf = io.BytesIO()
plt.savefig(buf, format='png')
buf.seek(0)
img_str = base64.b64encode(buf.read()).decode('utf-8')
print(f"IMAGE_BASE64:{img_str}")
plt.close()
"""
    # Customize the title based on the prompt
    title = last_message.replace("'", "").replace('"', "")
    generated_code = code_template.replace("{title}", title)
    
    return {
        "code": generated_code, 
        "messages": [AIMessage(content=f"I have generated code for: {title}")]
    }

def execute_code_node(state: AgentState):
    """
    Executes the generated Python code and captures the output.
    """
    code = state['code']
    old_stdout = sys.stdout
    redirected_output = sys.stdout = StringIO()
    
    try:
        # Create a restricted globals dictionary for safety (basic sandbox)
        exec_globals = {
            "pd": pd,
            "plt": plt,
            "io": io,
            "base64": base64,
            "sys": sys,
        }
        
        # Execute the code
        exec(code, exec_globals)
        
        sys.stdout = old_stdout
        output = redirected_output.getvalue()
        return {"output": output, "error": None}
        
    except Exception as e:
        sys.stdout = old_stdout
        return {"output": None, "error": str(e)}

# Define the graph
workflow = StateGraph(AgentState)

# Add nodes
workflow.add_node("generate_code", generate_code_node)
workflow.add_node("execute_code", execute_code_node)

# Define edges
workflow.set_entry_point("generate_code")
workflow.add_edge("generate_code", "execute_code")
workflow.add_edge("execute_code", END)

# Compile the graph
app = workflow.compile()

def run_agent(prompt: str):
    """
    Runs the agent workflow with the given prompt.
    """
    inputs = {"messages": [HumanMessage(content=prompt)], "code": "", "output": "", "error": ""}
    result = app.invoke(inputs)
    return result

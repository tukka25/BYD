import sys
import os

# Ensure backend directory is in path
sys.path.append(os.path.abspath("backend"))

from app.services.agents.workflow import run_agent_workflow
import json

def test_run():
    query = "Show me the sales trend for electronics over time"
    print(f"Running query: '{query}'...")
    
    try:
        result = run_agent_workflow(query)
        
        print("\n--- Workflow Result ---")
        if "error" in result and result["error"]:
            print(f"Error: {result['error']}")
        else:
            print("Success!")
            print(f"Plan: {json.dumps(result.get('plan', {}), indent=2)}")
            print(f"Data Context: {json.dumps(result.get('data_context', {}), indent=2)}")
            print(f"Generated Code:\n{result.get('code', '')}")
            print(f"Execution Output: {result.get('execution_result', {}).get('output', '')[:200]}...") # Truncated
            
    except Exception as e:
        print(f"Workflow crashed: {e}")

if __name__ == "__main__":
    test_run()

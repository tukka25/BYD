import sys
from io import StringIO
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import logging
import traceback
from typing import Dict, Any, Optional

class SafeExecutor:
    """
    Executes Python code in a controlled environment.
    IMPORTANT: This is still running code in the host process.
    For true sandboxing, this should be moved to a Docker container or isolated process.
    """
    
    def __init__(self):
        self.allowed_modules = {
            'pandas': pd,
            'pd': pd,
            'plotly.express': px,
            'px': px,
            'plotly.graph_objects': go,
            'go': go,
            'json': json
        }
    
    def execute(self, code: str, dataframe: pd.DataFrame) -> Dict[str, Any]:
        """
        Executes the provided code with the given DataFrame available as `df`.
        Returns the captured stdout (expected to be JSON figure) or error.
        """
        
        # Prepare execution context
        exec_globals = {**self.allowed_modules}
        exec_globals['df'] = dataframe
        
        # Capture stdout
        old_stdout = sys.stdout
        redirected_output = sys.stdout = StringIO()
        
        try:
            # Clean code if it contains markdown blocks
            code = code.replace("```python", "").replace("```", "").strip()
            
            exec(code, exec_globals)
            
            output = redirected_output.getvalue()
            
            # Try to parse the output as JSON to verify it's a valid Plotly figure
            try:
                figure_json = json.loads(output)
                return {"success": True, "figure": figure_json, "output": output}
            except json.JSONDecodeError:
                return {"success": False, "error": "Output is not valid JSON", "output": output}
                
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": str(e), "traceback": traceback.format_exc()}
        finally:
            sys.stdout = old_stdout

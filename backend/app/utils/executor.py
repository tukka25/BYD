import sys
from io import StringIO
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import json
import logging
import traceback
import re
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
        self.blocked_patterns = [
            r"\bimport\s+os\b",
            r"\bimport\s+subprocess\b",
            r"\bfrom\s+os\s+import\b",
            r"\bfrom\s+subprocess\s+import\b",
            r"\bopen\(",
            r"\beval\(",
            r"\bexec\(",
            r"\b__import__\(",
        ]

    def _sanitize_code(self, code: str) -> str:
        """
        Normalize generated output into executable Python.
        Handles markdown fences, smart quotes, and leading prose.
        """
        if not code:
            return ""

        code = code.replace("“", "\"").replace("”", "\"").replace("’", "'").replace("‘", "'")

        fenced = re.findall(r"```(?:python)?\s*(.*?)```", code, flags=re.DOTALL | re.IGNORECASE)
        if fenced:
            code = fenced[0]

        lines = code.splitlines()
        start_idx = 0
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if re.match(r"^(import |from |df\[|fig\s*=|[A-Za-z_]\w*\s*=|if |for |while |try:|except |print\(|#)", stripped):
                start_idx = idx
                break
        code = "\n".join(lines[start_idx:]).strip()
        return code

    def _is_safe_code(self, code: str) -> Optional[str]:
        lowered = code.lower()
        for pattern in self.blocked_patterns:
            if re.search(pattern, lowered):
                return f"Blocked unsafe pattern: {pattern}"
        return None
    
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
            code = self._sanitize_code(code)
            safety_error = self._is_safe_code(code)
            if safety_error:
                return {"success": False, "error": safety_error}
            
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

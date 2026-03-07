from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.graph_agent import run_agent

router = APIRouter()

class DashboardRequest(BaseModel):
    prompt: str
    data_source: Optional[str] = None # path to CSV or similar

class DashboardResponse(BaseModel):
    dashboard_html: str
    metadata: Dict[str, Any]

@router.post("/generate", response_model=DashboardResponse)
async def generate_dashboard(request: DashboardRequest):
    """
    Generate a dashboard based on the user prompt using SLM.
    """
    try:
        # Run the agent
        result = run_agent(request.prompt)
        
        # Extract the image from the execution output
        output = result.get("output", "")
        # Look for the marker
        import re
        match = re.search(r"IMAGE_BASE64:(.*)", output)
        if match:
            img_base64 = match.group(1).strip()
            html_content = f'<img src="data:image/png;base64,{img_base64}" alt="Generated Graph" />'
        else:
            html_content = f"<div>No graph generated. Output: {output}</div>"
            
        return {
            "dashboard_html": html_content,
            "metadata": {
                "model": "qwen:3b-8b (simulated)",
                "agent_steps": [m.content for m in result.get("messages", [])]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

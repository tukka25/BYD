from pathlib import Path
from typing import TypedDict, Annotated, Sequence, Dict, Any, List, Optional
import logging
import time
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from app.services.agents.planner import PlannerAgent
from app.services.agents.data_detective import DataDetective
from app.services.agents.chartist import ChartistAgent
from app.services.qwen_slm import LocalQwenChatModel
from app.utils.executor import SafeExecutor
from app.core.config import get_settings
import pandas as pd
import json

# Define the state
class AgentState(TypedDict):
    user_query: str
    selected_source: str
    available_sources: List[Dict[str, Any]]
    messages: Sequence[BaseMessage]
    plan: Dict[str, Any]
    source_decision: Dict[str, Any]
    data_context: Dict[str, Any]
    code: str
    execution_result: Dict[str, Any]
    error: str

settings = get_settings()
model_name = settings.OLLAMA_MODEL
logger = logging.getLogger(__name__)
data_dir = Path("/app/uploads")
if not data_dir.exists():
    data_dir = Path("backend/data")

# Initialize components
llm_json = LocalQwenChatModel(model=model_name, format="json")
llm_code = LocalQwenChatModel(model=model_name)
llm_tools = LocalQwenChatModel(model=model_name)

planner = PlannerAgent(llm_json)
detective = DataDetective(data_dir=str(data_dir), llm=llm_tools)
chartist = ChartistAgent(llm_code)
executor = SafeExecutor()

# 1. Planner Node
def planning_node(state: AgentState):
    started_at = time.perf_counter()
    query = state.get("user_query", "")
    if not query:
        query = state["messages"][-1].content
    logger.info("[workflow/planner] start query=%s", query[:120])
    
    plan = planner.create_plan(query)

    # Ensure it's a dict (Pydantic model -> dict)
    if hasattr(plan, 'dict'):
        plan = plan.dict()
    
    elapsed = time.perf_counter() - started_at
    logger.info(
        "[workflow/planner] done in %.2fs viz_type=%s",
        elapsed,
        plan.get("visualization_type"),
    )

    return {
        "plan": plan, 
        "messages": [AIMessage(content=f"Planning complete: {plan.get('steps')}")]
    }

# 2. Data Detective Node
def data_sourcing_node(state: AgentState):
    started_at = time.perf_counter()
    query = state.get("user_query", "")
    logger.info("[workflow/detective] start query=%s", query[:120])
    print("[detective] Step 0: start data source resolution")

    selected_source = state.get("selected_source", "")
    available_sources = state.get("available_sources", [])
    plan = state.get("plan", {})
    print(f"--------\nplan: {plan}\n--------\n")

    # print(f"[detective] Step 1: explicit selected_source='{selected_source}'")
    # print(f"[detective] Step 2: available_sources_count={len(available_sources)}")
    # print("[detective] Step 3: running detect_source(query + plan)")
    decision = detective.detect_source(
        query=query,
        plan=plan,
        selected_source=selected_source,
        available_sources=available_sources or None,
    )
    print(
        "[detective] Step 4: decision reason=%s confidence=%.2f"
        % (decision.get("reason"), float(decision.get("confidence", 0.0)))
    )
    selected = decision.get("selected")
    if not selected:
        print("[detective] Step 5: no selected source, stopping detective node")
        logger.warning(
            "[workflow/detective] unresolved source reason=%s candidates=%s",
            decision.get("reason"),
            [c.get("name") for c in decision.get("candidates", [])],
        )
        return {
            "error": (
                f"Could not resolve data source ({decision.get('reason')}). "
                "Please select a specific file/source."
            ),
            "source_decision": decision,
            "messages": [AIMessage(content="Could not confidently resolve the data source.")],
        }

    print(f"[detective] Step 5: selected source='{selected.get('name')}'")
    print("[detective] Step 6: loading schema for selected source")
    schema = detective.get_schema(selected.get("path") or selected.get("name"))
    
    if "error" in schema:
        print(f"[detective] Step 7: schema load failed error='{schema['error']}'")
        logger.error("[workflow/detective] schema error: %s", schema["error"])
        return {"error": schema["error"], "messages": [AIMessage(content=f"Error reading schema: {schema['error']}")]}
    print("[detective] Step 7: schema loaded successfully")
    elapsed = time.perf_counter() - started_at
    logger.info(
        "[workflow/detective] done in %.2fs filename=%s confidence=%.2f reason=%s",
        elapsed,
        schema.get("filename"),
        float(decision.get("confidence", 0.0)),
        decision.get("reason"),
    )
        
    return {
        "source_decision": decision,
        "data_context": schema,
        "messages": [AIMessage(content=f"Found data in {schema.get('filename')}")]
    }

# 3. Chartist Node
def coding_node(state: AgentState):
    started_at = time.perf_counter()
    plan = state["plan"]
    data_context = state["data_context"]
    source_decision = state.get("source_decision", {})
    dataframe_plan = source_decision.get("dataframe_plan", {})
    logger.info(
        "[workflow/chartist] start viz_type=%s columns=%s selected_columns=%s",
        plan.get("visualization_type"),
        len(data_context.get("columns", [])),
        len(dataframe_plan.get("selected_columns", [])) if isinstance(dataframe_plan, dict) else 0,
    )
    
    code = chartist.generate_code(
        plan,
        data_context,
        dataframe_plan=dataframe_plan if isinstance(dataframe_plan, dict) else {},
    )
    print(f"code: {code}")
    elapsed = time.perf_counter() - started_at
    logger.info("[workflow/chartist] done in %.2fs code_length=%s", elapsed, len(code))

    return {
        "code": code,
        "messages": [AIMessage(content="Generated Python code for visualization.")]
    }

# 4. Executor Node
def execution_node(state: AgentState):
    started_at = time.perf_counter()
    code = state["code"]
    data_context = state["data_context"]
    
    # Load actual dataframe for execution
    filepath = str(data_dir / data_context["filename"])
    filepath = data_context.get("filepath", filepath)
    try:
        if filepath.endswith('.csv'):
            df = pd.read_csv(filepath)
        elif filepath.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(filepath)
        else:
            raise ValueError("Unsupported format")
    except Exception as e:
        logger.error("[workflow/executor] data load failed: %s", e)
        return {"error": f"Failed to load data: {e}"}

    result = executor.execute(code, df)
    
    if result.get("success"):
        elapsed = time.perf_counter() - started_at
        logger.info("[workflow/executor] success in %.2fs", elapsed)
        return {
            "execution_result": result,
            "messages": [AIMessage(content="Successfully executed visualization code.")]
        }
    else:
        logger.error("[workflow/executor] failed: %s", result.get("error"))
        return {
            "error": result.get("error"),
            "messages": [AIMessage(content=f"Execution failed: {result.get('error')}")]
        }

# Define the graph
workflow = StateGraph(AgentState)

workflow.add_node("planner", planning_node)
workflow.add_node("detective", data_sourcing_node)
workflow.add_node("chartist", coding_node)
workflow.add_node("executor", execution_node)

workflow.set_entry_point("planner")

workflow.add_edge("planner", "detective")
workflow.add_edge("detective", "chartist")
workflow.add_edge("chartist", "executor")
workflow.add_edge("executor", END)

app = workflow.compile()

def run_agent_workflow(
    query: str,
    selected_source: str = "",
    available_sources: Optional[List[Dict[str, Any]]] = None,
):
    """
    Runs the full agent workflow with the given query.
    """
    
    # Temporary test defaults as requested.
    test_file = "/app/uploads/abu_dhabi_population_density.csv"
    forced_selected_source = test_file
    forced_available_sources = [
        {
            "id": "abu_dhabi_population_density.csv",
            "name": "abu_dhabi_population_density.csv",
            "type": "file",
            "path": test_file,
        }
    ]

    print(f"[workflow] using forced selected_source='{forced_selected_source}'")
    print(f"[workflow] using forced available_sources={forced_available_sources}")

    initial_state = {
        "user_query": query,
        "selected_source": forced_selected_source,
        "available_sources": forced_available_sources,
        "messages": [HumanMessage(content=query)],
        "plan": {},
        "source_decision": {},
        "data_context": {},
        "code": "",
        "execution_result": {},
        "error": ""
    }
    
    started_at = time.perf_counter()
    logger.info("[workflow] invoke start query=%s", query[:120])
    result = app.invoke(initial_state)
    elapsed = time.perf_counter() - started_at
    logger.info("[workflow] invoke done in %.2fs error=%s", elapsed, bool(result.get("error")))
    return result

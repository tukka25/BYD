# LangGraph Tool-Calling Detective

This folder contains a LangGraph/LangChain tool-calling architecture for datasource detection.

## Files

- `tools.py`
  - `list_available_sources(data_dir, db_url="")`
  - `read_source_headers(source, data_dir, db_url="")`
  - `verify_source_relevance(source, query, data_dir, db_url="", limit_rows=200)`
- `registry.py`: tool registry builder
- `detective_graph.py`: `create_react_agent` setup and invoke helper

## Behavior

1. List sources (files + DB tables)
2. Read headers/sample for candidate sources
3. Verify whether query intent exists in source via token overlap confidence

## Source formats

- Files: `.csv`, `.xlsx`, `.xls`
- DB: `db:<table_name>`

## Example

```python
from app.services.qwen_slm import LocalQwenChatModel
from langchain_archeticture.detective_graph import build_detective_agent, run_detective

llm = LocalQwenChatModel(model="qwen3.5:4b")
agent = build_detective_agent(llm, data_dir="backend/uploads", db_url="")
result = run_detective(agent, query="monthly sales by region")
```

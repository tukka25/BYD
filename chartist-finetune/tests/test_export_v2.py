from export_v2 import spec_prompt, split_by_schema

PROMPT = "Task: Where is churn highest?\n\nDataFrame `df` schema:\ncolumns: ['a']\n\nWrite the Python now."
SPEC = {"title": "Churn", "question": "Where is churn highest?", "chart": "bar", "table": "t", "x": "a",
        "y": "", "group": "", "agg": "count", "grain": "", "sort": "", "top_n": 0}


def test_spec_prompt_swaps_only_the_task():
    text = spec_prompt(PROMPT, SPEC)
    assert text.startswith("Task: Where is churn highest?\n\nChart plan:\n- chart: bar")
    assert text.endswith("DataFrame `df` schema:\ncolumns: ['a']\n\nWrite the Python now.")


def test_split_keeps_schemas_whole_and_disjoint():
    rows = [{"schema_id": f"s{i % 10}"} for i in range(100)]
    splits = split_by_schema(rows, 0.2, 7)
    train = {r["schema_id"] for r in splits["train"]}
    valid = {r["schema_id"] for r in splits["valid"]}
    assert train and valid and not train & valid and len(splits["train"]) + len(splits["valid"]) == 100

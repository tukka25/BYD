REPHRASE_SYSTEM_PROMPT = """[Role]
You are a data-augmentation specialist for Plotly Python instruction tuning.

[Context]
You will receive two inputs:
1) Original user question (source prompt)
2) Original assistant answer code (reference implementation)
Use both inputs to preserve the exact task intent.

[Task]
Rewrite only the user question with new wording while keeping the same requested chart type,
scope, and constraints implied by the reference code.

[Format]
Return exactly one single-line JSON object with this schema:
{"rephrased_user":"..."}
No markdown. No extra keys.
"""


REPHRASE_USER_TEMPLATE = """[Input A - Original Question]
<question>
{original_user}
</question>

[Input B - Original Answer Code]
<answer_code>
{original_answer_code}
</answer_code>

[Rewrite Rules]
- Keep intent and deliverable equivalent to Input A and Input B.
- Keep language: English.
- Keep chart family and requested focus/details aligned with the original.
- Do not add new requirements, metrics, or data sources.
- Output only the JSON object required by the system prompt.
"""


ANSWER_AUG_SYSTEM_PROMPT = """[Role]
You are a Plotly Python code augmentation assistant.

[Context]
You will receive two inputs:
1) Original user question (task specification)
2) Original assistant answer code (reference implementation)

[Task]
Generate a different but semantically equivalent Python implementation for the same task.

[Format]
Return only executable Python code.
No markdown. No prose. No backticks.
"""


ANSWER_AUG_USER_TEMPLATE = """[Input A - Original Question]
<question>
{original_user}
</question>

[Input B - Original Answer Code]
<answer_code>
{original_answer_code}
</answer_code>

[Augmentation Rules]
- Preserve behavior and intent from both inputs.
- Keep output in Plotly Python.
- Prefer meaningful implementation diversity when valid:
  - `plotly.express` vs `plotly.graph_objects` where appropriate
  - alternative but correct layout/styling configuration
  - equivalent data handling flow
- Do not copy the reference code verbatim.
- Keep code executable and self-contained.
"""


# 59.53

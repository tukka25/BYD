# Task 6 report: PAUSED after pilot (full run NOT started)

## Pilot (30 train questions, k=2, round 2 for failures)
- Verified 24/30, yield 0.80 (passes the 0.50 gate). Spend $0.1560 (a1 $0.1416 / 60 req, a2 $0.0144 / 6 req).
- cost_per_verified_row $0.0065; projection 0.0065 x 1920 = $12.48 (< $14.00 gate).
- Round 1: 24/30 kept (47/60 candidates passed). Round 2: 0/6 recovered.
- Refusals 0, unparsed 0, errored 0.
- Rejection reasons (66 candidates judged, 19 rejected): unknown_columns 18, execution_error 1, wrong_chart_type 0.
- Per-bucket yield: area 0.00, bar 0.857, box 1.0, gauge 1.0, grouped_or_stacked_bar 0.667, heatmap 0.75, histogram 1.0, line 1.0, pie 0.75, scatter 1.0, treemap_funnel_waterfall 1.0.
- Batches: msgbatch_01LpAC53bDmWNLD7cikowPNd, msgbatch_018PXqHrwaMbHJ5ZCNtauXbY.

## Why I stopped: unknown_columns is a false-positive gate
I spent $0.0147 (diag-targets batch msgbatch_01KKeXdTEdWGe8UF1agbTGwT) regenerating the 6 failed pilot questions and inspecting the code. All 6 are CORRECT charts rejected because they name DERIVED columns (ticket_count, week, month, users, revenue created by groupby/agg/reset_index(name=...)/value_counts) in x=/y=/color=. `_unknown_columns` flags any string in column position not in the original schema, so every count/aggregate-then-plot chart is rejected. Effect: area bucket 0% yield, systematic bias of the training set away from aggregation charts (the most common dashboard pattern), and ~27% of candidates wasted. Scaled to the full run this wastes budget and skews the data. Real unknown columns already fail at execution (KeyError) so the static check is largely redundant. Suggested fix (oracle change, your call): only flag a name unknown if it is never introduced in the code (name=, columns=, rename, assign, agg named tuples, df[...]= assignment, .columns = [...]), or drop the static check and rely on execution.

## Parallel validation (coordinator addition) - done
- `run_candidates` added to executor.py; gen_targets.py submit() restructured into collect / parallel-validate (8 workers) / judge-by-index phases, first survivor wins, rejected candidates logged to runs/targets_rejected.jsonl.
- Sanity check: 24 pilot kept targets, serial vs parallel verdicts identical (ok, figure_type, violations, unknown_columns). Serial 9.4s vs parallel 1.7s (5.5x).

## Spend
Task 6 so far: $0.1560 pilot + $0.0147 diagnostic = $0.1707. Project total per runs/spend.jsonl: $0.3713.

## Note
custom_id cannot contain '#'; the brief's separator was changed to '__'. Nothing committed (pilot data/targets.jsonl is only 24 rows).

## Five kept pilot targets (verbatim)
### s0000-q01 (bar, hard_case=None, figure_type=bar)
Question: How many daily active users come from each country?
```python
import plotly.express as px

agg = df.groupby('userCountry', as_index=False)['dailyActiveUsers'].sum().sort_values('dailyActiveUsers', ascending=False)
fig = px.bar(agg, x='userCountry', y='dailyActiveUsers', title='Daily Active Users by Country', labels={'userCountry': 'Country', 'dailyActiveUsers': 'Daily Active Users'})
print(fig.to_json())
```

### s0000-q05 (bar, hard_case=ambiguous_question, figure_type=bar)
Question: How's the app doing in different places?
```python
import plotly.express as px

agg = df.groupby('userCountry', as_index=False).agg(totalRevenue=('totalRevenue', 'sum'), dailyActiveUsers=('dailyActiveUsers', 'sum'))
agg = agg.sort_values('totalRevenue', ascending=False)
fig = px.bar(agg, x='userCountry', y='totalRevenue', color='dailyActiveUsers', color_continuous_scale='Blues', labels={'userCountry': 'Country', 'totalRevenue': 'Total Revenue', 'dailyActiveUsers': 'Total DAU'}, title='App Performance by Country: Total Revenue (color = Daily Active Users)')
fig.update_layout(xaxis_tickangle=-45)
print(fig.to_json())
```

### s0000-q14 (pie_or_donut, hard_case=multi_column_aggregation, figure_type=pie)
Question: What share of total revenue and sessions does each acquisition channel account for?
```python
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

agg = df.groupby('acquisitionChannel', as_index=False)[['totalRevenue', 'sessionCount']].sum()

fig = make_subplots(rows=1, cols=2, specs=[[{'type': 'domain'}, {'type': 'domain'}]], subplot_titles=['Share of Total Revenue', 'Share of Total Sessions'])
fig.add_trace(go.Pie(labels=agg['acquisitionChannel'], values=agg['totalRevenue'], hole=0.4, name='Revenue', textinfo='percent+label'), row=1, col=1)
fig.add_trace(go.Pie(labels=agg['acquisitionChannel'], values=agg['sessionCount'], hole=0.4, name='Sessions', textinfo='percent+label'), row=1, col=2)
fig.update_layout(title_text='Revenue and Sessions Share by Acquisition Channel', showlegend=True)

print(fig.to_json())
```

### s0001-q03 (scatter, hard_case=missing_field, figure_type=scatter)
Question: Is there a link between agent response time and satisfaction?
```python
import plotly.express as px

fig = px.scatter(df, x='ticket_resolution_hours', y='ticket_csat_score', color='ticket_priority', opacity=0.7, title='Resolution Time vs CSAT Score', labels={'ticket_resolution_hours': 'Resolution Time (hours)', 'ticket_csat_score': 'CSAT Score', 'ticket_priority': 'Priority'})
fig.update_layout(template='plotly_white')
print(fig.to_json())
```

### s0000-q04 (pie_or_donut, hard_case=None, figure_type=pie)
Question: What share of sessions comes from each platform?
```python
import plotly.express as px

agg = df.groupby('appPlatform', as_index=False)['sessionCount'].sum()
fig = px.pie(agg, names='appPlatform', values='sessionCount', hole=0.4, title='Share of Sessions by Platform')
fig.update_traces(textinfo='percent+label')
print(fig.to_json())
```

## Self-review
- Kept targets run against real CSV and use real columns; verified by the oracle. I only read 5 by eye in the pilot output above.
- Gate rejections were inspected on only 6 failures, but all 6 were the same false-positive pattern.
- Round-1 vs round-2 yield cannot be judged from a pilot where round 2 failed solely on the same false positive.

---
# FINAL (supersedes the pause above)
Ruling applied: execution is the oracle; `unknown_columns` is informational; `failure_kind` added.

## executor.py changes (surgical)
- `CandidateResult`: comment on `unknown_columns`; new `failure_kind` field.
- New `_HALLUCINATION` regex above `run_candidate`.
- `run_candidate`: `failure_kind` set on timeout / non-zero exit (hallucinated_column vs runtime_error) / bad JSON; final return `ok=not unknown` -> `ok=True`. `run_candidates` (parallel helper) added at end of file.
- tests: two new tests in tests/test_executor.py; full suite passes.

## Result (Stage A: 200 shuffled, k=2; Stage B: remaining 1720, k=1; seed 20261119)
- Verified 1902/1920, yield 0.991. Refusals 0.
- Spend: Stage A $0.9286, Stage B $4.1493 (a1 $4.0860, a2 $0.0633). Run total $5.0779; task total incl. pilot $0.1560 + diag $0.0147 = $5.2486. Project total $5.4492.
- Validation wall-clock: A 23.9s, B 102.1s (2,150 candidates).
- Rejections: runtime_error 44, creates_dataframe 6 (counts are candidates, over both stages and rounds). wrong_chart_type 0, hallucinated_column 0.
- Per-bucket yield: area 0.994, bar 0.997, box 1, gauge 1, grouped_or_stacked 1, heatmap 1, histogram 1, line 1, pie 1, scatter 0.922 (only bucket < 0.90-adjacent), time_series 1, treemap_funnel_waterfall 0.991.
- Stage B round 2: 24 retried, 8 recovered (attempt=2 rows). Stage B total 1704/1720 (1696 round 1 + 8 round 2); Stage A 198/200; union 1902/1920.

## The runtime_error stderr (all 10 from Stage A, verbatim last lines)
9x `ModuleNotFoundError: No module named 'statsmodels'` (plotly trendline="ols") and 1x `ValueError: Invalid frequency: M. Failed to parse with error message: ValueError("'M' is no longer supported for offsets. Please use 'ME' instead.")`. None are column errors, so the regex is correct and no pattern was added. Stage B's 34 further runtime errors: 33 more statsmodels, 1 `TypeError: treemap() got an unexpected keyword argument 'category_orders'`. Total statsmodels = 42.

## Pilot rows
data/targets.jsonl is built only from Stage A + B (pilot file moved to runs/pilot_backup/ and never loaded). 1902 unique question_ids, 0 test-split schemas. 24 pilot question_ids reappear because they are in the shuffled set; they were regenerated under the new gate (6 happen to have byte-identical code).

## Concerns
- Scatter (and by-extension trendline requests) lose ~8% because statsmodels is not installed in this venv: trendline="ols" is rejected. Training set therefore contains no trendline examples; if the backend env has statsmodels, those are legit lost targets. Backend requirements do not list statsmodels, so rejecting is consistent with deployment.
- The 'M' frequency error is pandas-version specific.

## Fix round 1
- `run_candidate` now always returns a CandidateResult: non-object stdout JSON -> `bad_output` (error names the type); post-parse block wrapped; empty traces -> `no_figure`; unreadable CSV -> `unreadable_input`. Static violations keep `failure_kind=None`.
- Tests added: payloads 5 / [1,2] / null / "text", empty figure, unreadable CSV, and `run_candidates` on a mixed list (full-length result, other verdicts intact). They fail on the old executor and pass now; full suite green.
- 30 random existing targets re-validated: verdicts and figure types unchanged. data/targets.jsonl untouched.

## Fix round 2
- executor.py: `run_candidate` is now a thin total wrapper (try/except Exception -> ok=False, failure_kind=runtime_error, error=type+message) around the previous body, renamed `_run_candidate` (signature line moved; body otherwise unchanged). Parse except widened to (ValueError, IndexError, RecursionError) -> bad_output (covers huge ints, deep nesting). Figure check: `data` must be a list; a non-empty list must start with a dict, else bad_output; untyped dict trace still defaults to scatter; empty list -> no_figure.
- Tests added: non-UTF-8 stdout, 10k-digit integer, deep nesting, lone surrogate, patched OSError, five garbage figure shapes, untyped-dict default, run_candidates with a raising job (full-length list). Suite: 47 passed.
- 30 existing targets re-validated: verdicts and figure types unchanged. targets.jsonl untouched.

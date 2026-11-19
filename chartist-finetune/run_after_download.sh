#!/usr/bin/env bash
# Unattended chain: wait for the model download, then gate -> train -> eval.
#
#   cd chartist-finetune && ./run_after_download.sh
#
# Safe to start while the download is still running; it waits. Keep the machine
# plugged in. Everything runs under caffeinate so the lid closing is fine.
#
# In the morning:
#   cat runs/chain/STATUS
#   .venv/bin/python summarize_run.py runs/lora-v1/train.log
#   cat data/eval_report.json | python3 -m json.tool | head -40
#
# Each stage writes its own log under runs/chain/ and the chain stops at the
# first failure rather than carrying a broken artefact forward.

set -uo pipefail
cd "$(dirname "$0")"

MODEL="${MODEL:-models/qwen3.5-9b-4bit}"
DATA="${DATA:-data/mlx}"
ADAPTERS="${ADAPTERS:-runs/lora-v1/adapters}"
MAXLEN="${MAXLEN:-4096}"
ITERS="${ITERS:-1930}"
BATCH="${BATCH:-2}"
WAIT_LIMIT_MIN="${WAIT_LIMIT_MIN:-240}"   # give up waiting on the download after this

PY=.venv/bin/python
CHAIN=runs/chain
mkdir -p "$CHAIN" "$(dirname "$ADAPTERS")"
STATUS="$CHAIN/STATUS"

say() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$CHAIN/chain.log"; }
stage() { echo "$1" > "$STATUS"; say "=== $1 ==="; }
die() { stage "FAILED: $1"; say "see $CHAIN/ for logs"; exit 1; }

say "chain started; waiting for the download to finish (limit ${WAIT_LIMIT_MIN} min)"
stage "waiting for download"

# --- 1. wait for the download ----------------------------------------------
# Complete means: no hf download process, both shards present as real files,
# and no .incomplete left behind. Checking all three avoids starting on a
# half-written model, which would fail in a confusing way much later.
deadline=$(( $(date +%s) + WAIT_LIMIT_MIN * 60 ))
last_size=0
stall_count=0
while :; do
    running=$(pgrep -f "hf download mlx-community" | wc -l | tr -d ' ')
    shards=$(ls -1 "$MODEL"/*.safetensors 2>/dev/null | wc -l | tr -d ' ')
    incomplete=$(find "$MODEL" -name "*.incomplete" 2>/dev/null | wc -l | tr -d ' ')
    size=$(du -sk "$MODEL" 2>/dev/null | cut -f1 || echo 0)

    if [ "$running" -eq 0 ] && [ "$shards" -ge 1 ] && [ "$incomplete" -eq 0 ]; then
        say "download complete: $((size/1024)) MB, $shards shard(s)"
        break
    fi
    if [ "$(date +%s)" -gt "$deadline" ]; then
        die "download did not finish within ${WAIT_LIMIT_MIN} min (at $((size/1024)) MB)"
    fi
    # If no process is running and it is not complete, the download died.
    if [ "$running" -eq 0 ] && [ "$incomplete" -gt 0 ]; then
        die "download process gone but $incomplete .incomplete file(s) remain -- it died partway; re-run the hf download"
    fi
    if [ "$size" -eq "$last_size" ]; then
        stall_count=$((stall_count + 1))
    else
        stall_count=0
    fi
    # du granularity means short windows read zero; 20 x 60s of no growth is real.
    [ "$stall_count" -ge 20 ] && die "download stalled for 20 min at $((size/1024)) MB"
    last_size=$size
    sleep 60
done

# --- 2. prove the model loads ----------------------------------------------
stage "verifying the model loads"
"$PY" - <<'PYEOF' > "$CHAIN/01_model_load.log" 2>&1
import sys
from mlx_lm import load
model, tok = load(sys.argv[1] if len(sys.argv) > 1 else "models/qwen3.5-9b-4bit")
print("model and tokenizer loaded")
PYEOF
[ $? -eq 0 ] || die "the model directory will not load (see $CHAIN/01_model_load.log)"
say "model loads"

# --- 3. the token gate ------------------------------------------------------
# Hard stop. mlx-lm truncates an over-length row's tail silently, and the tail is
# print(fig.to_json()) -- the one line the contract requires.
stage "token-length gate"
"$PY" check_token_lengths.py --model "$MODEL" --data "$DATA" --limit "$MAXLEN" \
    > "$CHAIN/02_token_gate.log" 2>&1
if [ $? -ne 0 ]; then
    tail -20 "$CHAIN/02_token_gate.log" | tee -a "$CHAIN/chain.log"
    die "token gate: at least one row exceeds --max-seq-length $MAXLEN. Raise MAXLEN and re-run."
fi
say "token gate passed"
grep -E "^  (train|valid)|^PASS" "$CHAIN/02_token_gate.log" | tee -a "$CHAIN/chain.log"

# --- 4. train ---------------------------------------------------------------
stage "training ($ITERS iters)"
say "this is the long one; mlx-lm prints its own progress into the log"
"$PY" -m mlx_lm lora \
    --model "$MODEL" --train --data "$DATA" \
    --adapter-path "$ADAPTERS" \
    --batch-size "$BATCH" --max-seq-length "$MAXLEN" --iters "$ITERS" \
    --steps-per-report 10 --steps-per-eval 150 --save-every 200 \
    --val-batches -1 --seed 42 --mask-prompt \
    > "$(dirname "$ADAPTERS")/train.log" 2>&1
[ $? -eq 0 ] || die "training failed (see $(dirname "$ADAPTERS")/train.log)"
say "training finished"
"$PY" summarize_run.py "$(dirname "$ADAPTERS")/train.log" | tee -a "$CHAIN/chain.log"

# --- 5. evaluate the base model --------------------------------------------
# Base first so there is a baseline on disk even if the adapter eval fails.
stage "evaluating base"
"$PY" evaluate.py --model "$MODEL" --adapter-path none --label base \
    > "$CHAIN/03_eval_base.log" 2>&1
[ $? -eq 0 ] || say "WARNING base eval failed (see $CHAIN/03_eval_base.log); continuing"

# --- 6. evaluate the adapter -----------------------------------------------
stage "evaluating lora-v1"
"$PY" evaluate.py --model "$MODEL" --adapter-path "$ADAPTERS" --label lora-v1 \
    > "$CHAIN/04_eval_lora.log" 2>&1
[ $? -eq 0 ] || die "adapter eval failed (see $CHAIN/04_eval_lora.log)"

# --- 7. the headline --------------------------------------------------------
stage "DONE"
say "results:"
"$PY" - <<'PYEOF' 2>&1 | tee -a "$CHAIN/chain.log"
import json
from pathlib import Path
r = json.loads(Path("data/eval_report.json").read_text(encoding="utf-8"))
for label in ("base", "lora-v1"):
    if label in r:
        d = r[label]
        print(f"  {label:9s} render {d['render_rate']:.1%}  "
              f"quota-weighted {d.get('render_rate_quota_weighted') or 0:.1%}  "
              f"right-shape {d['right_shape_rate']:.1%}  "
              f"hallucinated {d['hallucinated_column_rate']:.1%}")
if "base" in r and "lora-v1" in r:
    delta = (r["lora-v1"]["render_rate"] - r["base"]["render_rate"]) * 100
    print(f"\n  delta {delta:+.1f} pp on render rate")
    print("  at n=300 per arm a gap under ~11 pp is not distinguishable from noise")
    print("  check by_bucket and by_hard_case in data/eval_report.json for where the gain is")
PYEOF
say "chain complete"

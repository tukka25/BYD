#!/usr/bin/env bash
# Unattended: worst-case memory gate -> train -> summarise -> eval base -> eval adapter.
#
#   cd chartist-finetune && nohup caffeinate -ims ./run_training_chain.sh \
#        > runs/chain/nohup.log 2>&1 & disown
#
# Launch it under `caffeinate -ims` exactly as above; the script does NOT wrap
# itself, so run bare it dies when the machine sleeps. Keep the machine plugged in.
#
# In the morning:
#   cat runs/chain/STATUS
#   cat runs/chain/chain.log
#
# Replaces run_after_download.sh (the model is already on disk). Differences that
# matter, all of them learned from the run that failed -- see README section 4b:
#
#  * Memory is gated by probe_mem.py on a SYNTHETIC worst-case batch, not by a
#    short smoke run. iterate_batches sorts by length and permutes, so a 12-iter
#    smoke test very likely never sees the longest batch -- it would pass, and
#    the real run would OOM hours later.
#  * --batch-size 1 --grad-accumulation-steps 2 replaces --batch-size 2. The
#    gradient is divided by the accumulation steps (tuner/trainer.py:257), so the
#    effective batch and the learning-rate semantics are unchanged, at half the
#    peak activation memory.
#  * --iters counts MICRO-steps under accumulation, so two epochs is 2x the row
#    count, derived below from the data rather than hardcoded.
#  * The capped dataset is used so no row is ever truncated. Truncation can make
#    the loss nan (empty mask -> 0/0) and one nan gradient poisons the run.
#  * If the first config does not fit, it escalates instead of giving up.

set -uo pipefail
cd "$(dirname "$0")"

MODEL="${MODEL:-models/qwen3.5-9b-4bit}"
DATA="${DATA:-data/mlx_1536}"
MAXLEN="${MAXLEN:-1536}"
ADAPTERS="${ADAPTERS:-runs/lora-v1/adapters}"
ACCUM="${ACCUM:-2}"          # effective batch = BATCH x ACCUM
BATCH="${BATCH:-1}"
EPOCHS="${EPOCHS:-2}"
EVAL_EVERY="${EVAL_EVERY:-650}"
SAVE_EVERY="${SAVE_EVERY:-200}"
SEED="${SEED:-42}"

PY=.venv/bin/python
CHAIN=runs/chain
mkdir -p "$CHAIN" "$(dirname "$ADAPTERS")"
STATUS="$CHAIN/STATUS"

say()   { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$CHAIN/chain.log"; }
stage() { echo "$1" > "$STATUS"; say "=== $1 ==="; }
die()   { stage "FAILED: $1"; say "see $CHAIN/ for logs"; exit 1; }

say "chain started"
stage "preflight"

# --- 1. preflight -----------------------------------------------------------
[ -x "$PY" ]                 || die "no venv at $PY"
[ -d "$MODEL" ]              || die "model missing at $MODEL"
[ -f "$DATA/train.jsonl" ]   || die "no $DATA/train.jsonl -- run cap_dataset.py --limit $MAXLEN --out $DATA"
[ -f "$DATA/valid.jsonl" ]   || die "no $DATA/valid.jsonl"
"$PY" -c 'import mlx.core as mx, sys; sys.exit(0 if "gpu" in str(mx.default_device()) else 1)' \
    || die "not on the GPU -- LoRA on CPU is not worth running"

ROWS=$(grep -c . "$DATA/train.jsonl")
ITERS="${ITERS:-$(( ROWS * EPOCHS / BATCH ))}"
say "data $DATA: $ROWS train rows -> $ITERS micro-steps for $EPOCHS epoch(s)"
say "effective batch $(( BATCH * ACCUM )) (batch $BATCH x accum $ACCUM), max-seq-length $MAXLEN"

# Report the memory situation, because that is what killed the previous run.
"$PY" - <<'PYEOF' 2>&1 | tee -a "$CHAIN/chain.log"
import mlx.core as mx, subprocess
info = mx.device_info()
sw = subprocess.run(["sysctl","-n","vm.swapusage"], capture_output=True, text=True).stdout.strip()
print(f"  GPU working set: {info['max_recommended_working_set_size']/1024**3:.2f} GB")
print(f"  swap: {sw}")
PYEOF

# --- 2. token gate ----------------------------------------------------------
# Hard stop: an over-length row gets truncated, and truncation can nan the run.
stage "token-length gate"
"$PY" check_token_lengths.py --model "$MODEL" --data "$DATA" --limit "$MAXLEN" \
    > "$CHAIN/01_token_gate.log" 2>&1 \
    || { tail -12 "$CHAIN/01_token_gate.log" | tee -a "$CHAIN/chain.log"
         die "token gate: a row exceeds $MAXLEN. Re-run cap_dataset.py at this limit."; }
grep -E "^  (train|valid)|^PASS" "$CHAIN/01_token_gate.log" | tee -a "$CHAIN/chain.log"

# --- 3. worst-case memory gate, escalating ---------------------------------
# Each candidate is tested on a synthetic batch of exactly MAXLEN tokens, which
# is the worst case the real run can hit. First one that fits wins.
stage "memory gate (worst-case $MAXLEN-token batch)"
CHOSEN=""
declare -a EXTRA_FLAGS
try_config() {                       # $1 = label, $2.. = extra lora flags
    local label="$1"; shift
    local log="$CHAIN/02_mem_${label}.log"
    say "  trying: $label"
    if "$PY" probe_mem.py --model "$MODEL" --lengths "$MAXLEN" --batch-size "$BATCH" \
            "$@" > "$log" 2>&1; then
        grep -E "^ *$MAXLEN|model loaded" "$log" | sed 's/^/      /' | tee -a "$CHAIN/chain.log"
        CHOSEN="$label"; EXTRA_FLAGS=("$@"); return 0
    fi
    say "      does not fit ($(grep -o 'OOM/err.*' "$log" | head -1 | cut -c1-60))"
    return 1
}
#   plain -> checkpointed -> checkpointed with half the LoRA layers.
#   grad-checkpoint costs ~25% speed, so it is not the first choice; num-layers 8
#   costs model capacity, so it is the last.
try_config "plain"            --num-layers 16 \
  || try_config "checkpoint"  --num-layers 16 --checkpoint \
  || try_config "checkpoint8" --num-layers 8  --checkpoint \
  || die "even 8 LoRA layers with checkpointing will not fit a $MAXLEN-token batch. Free more memory (README 4b) or lower MAXLEN via cap_dataset.py."
say "chosen config: $CHOSEN"

LORA_FLAGS=()
for f in "${EXTRA_FLAGS[@]}"; do
    [ "$f" = "--checkpoint" ] && LORA_FLAGS+=(--grad-checkpoint) || LORA_FLAGS+=("$f")
done

# --- 4. train ---------------------------------------------------------------
stage "training ($ITERS micro-steps, config $CHOSEN)"
say "mlx-lm renders its own progress into the log: tail -f $(dirname "$ADAPTERS")/train.log"
TRAIN_LOG="$(dirname "$ADAPTERS")/train.log"
"$PY" -m mlx_lm lora \
    --model "$MODEL" --train --data "$DATA" \
    --adapter-path "$ADAPTERS" \
    --batch-size "$BATCH" --grad-accumulation-steps "$ACCUM" \
    --max-seq-length "$MAXLEN" --iters "$ITERS" \
    --steps-per-report 25 --steps-per-eval "$EVAL_EVERY" --save-every "$SAVE_EVERY" \
    --val-batches -1 --seed "$SEED" --mask-prompt \
    "${LORA_FLAGS[@]}" > "$TRAIN_LOG" 2>&1
TRAIN_RC=$?
"$PY" summarize_run.py "$TRAIN_LOG" 2>&1 | tee -a "$CHAIN/chain.log"
[ $TRAIN_RC -eq 0 ] || die "training exited $TRAIN_RC (see $TRAIN_LOG)"
say "training finished"

# --- 5. evaluate, base first so a baseline exists on disk either way --------
stage "evaluating base"
"$PY" evaluate.py --model "$MODEL" --adapter-path none --label base \
    > "$CHAIN/03_eval_base.log" 2>&1 \
    || say "WARNING base eval failed (see $CHAIN/03_eval_base.log); continuing"

stage "evaluating lora-v1"
"$PY" evaluate.py --model "$MODEL" --adapter-path "$ADAPTERS" --label lora-v1 \
    > "$CHAIN/04_eval_lora.log" 2>&1 \
    || die "adapter eval failed (see $CHAIN/04_eval_lora.log)"

# --- 6. headline ------------------------------------------------------------
stage "DONE"
"$PY" - <<'PYEOF' 2>&1 | tee -a "$CHAIN/chain.log"
import json
from pathlib import Path
r = json.loads(Path("data/eval_report.json").read_text(encoding="utf-8"))
for label in ("base", "lora-v1"):
    if label in r:
        d = r[label]
        print(f"  {label:9s} render {d['render_rate']:.1%}  "
              f"quota-weighted {(d.get('render_rate_quota_weighted') or 0):.1%}  "
              f"right-shape {d['right_shape_rate']:.1%}  "
              f"hallucinated {d['hallucinated_column_rate']:.1%}")
if "base" in r and "lora-v1" in r:
    delta = (r["lora-v1"]["render_rate"] - r["base"]["render_rate"]) * 100
    print(f"\n  delta {delta:+.1f} pp on render rate")
    print("  at n=300 per arm a gap under ~11 pp is not distinguishable from noise")
    print("  see by_bucket / by_hard_case in data/eval_report.json for where it moved")
PYEOF
say "chain complete"

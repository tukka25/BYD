#!/usr/bin/env bash
# Overnight LoRA training run. Survives a closed lid, a closed terminal and a
# closed laptop display; does not survive a reboot or running out of disk.
#
#   cd chartist-finetune && ./run_overnight.sh
#
# Then close the terminal and go to bed. In the morning:
#   tail -40 runs/lora-v1/train.log
#   cat runs/lora-v1/overnight.log
#
# Override anything via the environment:
#   ITERS=1200 MAXLEN=2048 ./run_overnight.sh

set -euo pipefail
cd "$(dirname "$0")"

MODEL="${MODEL:-models/qwen3.5-9b-4bit}"
DATA="${DATA:-data/mlx}"
ADAPTERS="${ADAPTERS:-runs/lora-v1/adapters}"
ITERS="${ITERS:-1930}"          # 965 steps/epoch at batch 2 -> two epochs
BATCH="${BATCH:-2}"
MAXLEN="${MAXLEN:-2560}"        # above the longest row; see check_token_lengths.py
REPORT="${REPORT:-10}"
EVAL_EVERY="${EVAL_EVERY:-100}"
SAVE_EVERY="${SAVE_EVERY:-200}"

PY=.venv/bin/python
RUN_DIR="$(dirname "$ADAPTERS")"
mkdir -p "$RUN_DIR"
OUT="$RUN_DIR/overnight.log"

# --- preflight -------------------------------------------------------------
# Each of these costs seconds and prevents waking up to a wasted night.

[ -x "$PY" ] || { echo "no venv at $PY"; exit 1; }
[ -d "$MODEL" ] || { echo "model not found at $MODEL -- run mlx_lm.convert first"; exit 1; }
[ -f "$DATA/train.jsonl" ] || { echo "no $DATA/train.jsonl -- run export_mlx.py --valid-ratio 0.12"; exit 1; }
[ -f "$DATA/valid.jsonl" ] || { echo "no $DATA/valid.jsonl"; exit 1; }

echo "== token-length gate =="
# Hard gate. If any row exceeds MAXLEN, mlx-lm truncates its tail silently,
# cutting the closing print(fig.to_json()) and training the model to omit it.
"$PY" check_token_lengths.py --model "$MODEL" --data "$DATA" --limit "$MAXLEN"

echo
echo "== disk =="
df -h . | tail -1
# Adapters are small, but checkpoints every $SAVE_EVERY iterations add up.
avail_gb=$(df -g . | tail -1 | awk '{print $4}')
[ "$avail_gb" -ge 5 ] || { echo "only ${avail_gb}GB free -- want at least 5GB"; exit 1; }

echo
echo "== launching =="
echo "  model    $MODEL"
echo "  data     $DATA  ($(wc -l < "$DATA/train.jsonl" | tr -d ' ') train / $(wc -l < "$DATA/valid.jsonl" | tr -d ' ') valid)"
echo "  iters    $ITERS  (batch $BATCH, max-seq-length $MAXLEN)"
echo "  adapters $ADAPTERS"
echo "  log      $RUN_DIR/train.log"
echo "  wrapper  $OUT"
echo

# caffeinate -i  keeps the system awake while this runs
#            -m  keeps the disk awake
#            -s  keeps it awake even on battery (drop -s to allow sleep when unplugged)
# nohup + disown lets the terminal close without taking the job with it.
nohup caffeinate -ims "$PY" train_with_progress.py \
    --model "$MODEL" \
    --train \
    --data "$DATA" \
    --adapter-path "$ADAPTERS" \
    --batch-size "$BATCH" \
    --max-seq-length "$MAXLEN" \
    --iters "$ITERS" \
    --steps-per-report "$REPORT" \
    --steps-per-eval "$EVAL_EVERY" \
    --save-every "$SAVE_EVERY" \
    > "$OUT" 2>&1 &

PID=$!
disown "$PID" 2>/dev/null || true
echo "$PID" > "$RUN_DIR/train.pid"

echo "running as pid $PID"
echo
echo "watch it:   tail -f $OUT"
echo "loss only:  tail -f $RUN_DIR/train.log"
echo "stop it:    kill $PID"
echo
echo "Waiting 45s to confirm it got past model load..."
sleep 45
if kill -0 "$PID" 2>/dev/null; then
    echo "still alive. Last lines:"
    tail -5 "$OUT" | sed 's/^/    /'
    echo
    echo "If the progress bar is stuck at 0 but the log is filling with loss"
    echo "lines, the report format differs from the wrapper's regexes -- training"
    echo "is fine and fully logged, you have only lost the bar."
else
    echo "DIED within 45s. Output:"
    tail -30 "$OUT" | sed 's/^/    /'
    exit 1
fi

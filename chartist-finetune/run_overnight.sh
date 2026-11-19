#!/usr/bin/env bash
# Overnight LoRA training. Survives a closed lid, a closed terminal and battery;
# does not survive a reboot or running out of disk.
#
#   cd chartist-finetune && ./run_overnight.sh
#
# Then close the terminal. In the morning:
#   .venv/bin/python summarize_run.py runs/lora-v1/train.log
#
# Override via the environment:
#   ITERS=1200 MAXLEN=2048 MASK_PROMPT=0 ./run_overnight.sh
#
# Flags below were checked against mlx-lm 0.32.2's own --help (runs/mlx_help.txt).
# mlx-lm renders its own progress bar and loss lines (mlx_lm/cli_ui.py: TrainUI),
# so nothing here wraps or re-implements that; output is redirected to a log.

set -euo pipefail
cd "$(dirname "$0")"

MODEL="${MODEL:-models/qwen3.5-9b-4bit}"
DATA="${DATA:-data/mlx}"
ADAPTERS="${ADAPTERS:-runs/lora-v1/adapters}"
ITERS="${ITERS:-1930}"          # 965 steps/epoch at batch 2 -> two epochs
BATCH="${BATCH:-2}"
MAXLEN="${MAXLEN:-4096}"        # measured, not estimated: see check_token_lengths.py
REPORT="${REPORT:-10}"
EVAL_EVERY="${EVAL_EVERY:-150}"
SAVE_EVERY="${SAVE_EVERY:-200}"
SEED="${SEED:-42}"
MASK_PROMPT="${MASK_PROMPT:-1}" # see the note below -- on by default, deliberately

PY=.venv/bin/python
RUN_DIR="$(dirname "$ADAPTERS")"
mkdir -p "$RUN_DIR"
LOG="$RUN_DIR/train.log"

# --- preflight: seconds spent here beat waking up to a wasted night ---------

[ -x "$PY" ] || { echo "no venv at $PY"; exit 1; }
[ -d "$MODEL" ] || { echo "model not found at $MODEL -- download it first"; exit 1; }
[ -f "$DATA/train.jsonl" ] || { echo "no $DATA/train.jsonl -- run export_mlx.py --valid-ratio 0.12"; exit 1; }
[ -f "$DATA/valid.jsonl" ] || { echo "no $DATA/valid.jsonl"; exit 1; }

"$PY" -c 'import mlx.core as mx, sys; d=str(mx.default_device()); print("  device:", d); sys.exit(0 if "gpu" in d else 1)' \
  || { echo "not running on the GPU -- stop, LoRA on CPU is not worth the night"; exit 1; }

echo
echo "== token-length gate =="
# Hard gate. mlx-lm truncates an over-length row's tail silently, and the tail
# is print(fig.to_json()) -- the one line the chartist contract requires.
"$PY" check_token_lengths.py --model "$MODEL" --data "$DATA" --limit "$MAXLEN"

echo
echo "== disk =="
df -h . | tail -1
avail_gb=$(df -g . | tail -1 | awk '{print $4}')
[ "$avail_gb" -ge 5 ] || { echo "only ${avail_gb}GB free -- want at least 5GB for checkpoints"; exit 1; }

# --- training flags ---------------------------------------------------------
#
# --mask-prompt: compute the loss on the assistant turn only, not on the system
#   contract and schema block. Those are always supplied at inference, so
#   training on them spends capacity learning to emit prompts instead of code.
#   mlx-lm does NOT mask by default. Set MASK_PROMPT=0 to compare.
#
# --val-batches -1: evaluate on the whole validation set rather than a sample.
#   Valid is only 260 rows across 28 schemas, so a sampled val loss is noisy --
#   and val loss is the signal that decides when to stop. The full set costs
#   ~130 forward batches per eval, which is why EVAL_EVERY is 150 rather than
#   100: roughly a dozen evaluations across the run instead of twenty.
#
# --num-layers defaults to 16. Left alone for the first run; if the adapter
#   underfits (train loss plateaus high), try --num-layers 32 or -1.
# --grad-checkpoint trades speed for memory; add it only if this OOMs.

ARGS=(
    --model "$MODEL"
    --train
    --data "$DATA"
    --adapter-path "$ADAPTERS"
    --batch-size "$BATCH"
    --max-seq-length "$MAXLEN"
    --iters "$ITERS"
    --steps-per-report "$REPORT"
    --steps-per-eval "$EVAL_EVERY"
    --save-every "$SAVE_EVERY"
    --val-batches -1
    --seed "$SEED"
)
[ "$MASK_PROMPT" = "1" ] && ARGS+=(--mask-prompt)

echo
echo "== launching =="
echo "  model    $MODEL"
echo "  data     $DATA  ($(wc -l < "$DATA/train.jsonl" | tr -d ' ') train / $(wc -l < "$DATA/valid.jsonl" | tr -d ' ') valid)"
echo "  iters    $ITERS  (batch $BATCH, max-seq-length $MAXLEN)"
echo "  mask     $([ "$MASK_PROMPT" = "1" ] && echo "prompt masked (loss on the code only)" || echo "OFF -- loss over the whole sequence")"
echo "  adapters $ADAPTERS"
echo "  log      $LOG"
echo

# caffeinate -i keeps the system awake, -m the disk, -s even on battery.
# Drop -s if you would rather it sleep when unplugged.
# mlx-lm calls maybe_set_recommended_wired_limit() itself, so no sysctl needed.
# `python -m mlx_lm lora` is the current form; `python -m mlx_lm.lora` is deprecated.
nohup caffeinate -ims "$PY" -m mlx_lm lora "${ARGS[@]}" > "$LOG" 2>&1 &

PID=$!
disown "$PID" 2>/dev/null || true
echo "$PID" > "$RUN_DIR/train.pid"

echo "running as pid $PID"
echo
echo "watch:    tail -f $LOG"
echo "stop:     kill $PID"
echo "morning:  $PY summarize_run.py $LOG"
echo
echo "Waiting 60s to confirm it got past model load..."
sleep 60
if kill -0 "$PID" 2>/dev/null; then
    echo "still alive. Last lines:"
    tail -8 "$LOG" | sed 's/^/    /'
    echo
    echo "If you see iteration lines, it is training. Go to bed."
else
    echo "DIED within 60s. Output:"
    tail -30 "$LOG" | sed 's/^/    /'
    exit 1
fi

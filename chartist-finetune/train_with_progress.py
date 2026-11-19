#!/usr/bin/env python3
"""Run mlx_lm.lora with a tqdm progress bar, an ETA, and an overfitting watch.

mlx-lm prints a loss line every --steps-per-report iterations but has no progress
bar and no ETA, which makes an overnight run hard to judge. This wraps the CLI as
a subprocess and parses its own output, rather than calling mlx-lm's internals --
so it keeps working across versions and never changes how training behaves.

What it adds:
  * a tqdm bar over --iters, with it/s and a real ETA
  * live train loss, val loss and peak memory in the bar's postfix
  * an overfitting watch: it records every validation loss and tells you, in the
    morning, the iteration where val loss bottomed out and whether it rose after
  * every line mlx-lm printed, mirrored verbatim to a log file

Every unrecognised argument is passed straight through to mlx_lm.lora, so this is
a drop-in prefix:

    .venv/bin/python train_with_progress.py \
        --model models/qwen3.5-9b-4bit --train --data data/mlx \
        --adapter-path runs/lora-v1/adapters \
        --batch-size 2 --max-seq-length 2560 --iters 1930 \
        --steps-per-report 10 --steps-per-eval 100 --save-every 200

NOTE ON THE PARSING. mlx-lm's exact report wording varies between releases, and
this was written without a copy installed, so the regexes are deliberately loose
(they key off "Iter N:" and look for optional loss fields). Watch the first
minute: if the bar advances, parsing works. If it sits at zero while the log
fills with loss lines, the format has moved -- the run is still fine and fully
logged, you have just lost the bar. Adjust ITER_RE below in that case.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    from tqdm import tqdm
except ImportError:
    sys.exit("tqdm is not installed. Run: .venv/bin/python -m pip install tqdm")

# Loose on purpose -- see the note in the docstring.
ITER_RE = re.compile(r"\bIter\s+(\d+)\s*:", re.IGNORECASE)
TRAIN_LOSS_RE = re.compile(r"\bTrain(?:ing)?\s+loss\s+([0-9]*\.?[0-9]+)", re.IGNORECASE)
VAL_LOSS_RE = re.compile(r"\bVal(?:idation)?\s+loss\s+([0-9]*\.?[0-9]+)", re.IGNORECASE)
PEAK_MEM_RE = re.compile(r"\bPeak mem\s+([0-9]*\.?[0-9]+)\s*GB", re.IGNORECASE)
TOKENS_SEC_RE = re.compile(r"\bTokens?/sec\s+([0-9]*\.?[0-9]+)", re.IGNORECASE)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--iters", type=int, default=None)
    parser.add_argument("--adapter-path", default="runs/lora-v1/adapters")
    parser.add_argument("--progress-log", default=None, help="defaults to <adapter-path>/../train.log")
    parser.add_argument("-h", "--help", action="store_true")
    known, passthrough = parser.parse_known_args()

    if known.help:
        print(__doc__)
        print("\n--- mlx_lm.lora's own help follows ---\n", flush=True)
        return subprocess.call([sys.executable, "-m", "mlx_lm.lora", "--help"])

    if known.iters is None:
        return subprocess.call(
            [sys.executable, "-m", "mlx_lm.lora", *passthrough, "--adapter-path", known.adapter_path]
        )

    log_path = Path(known.progress_log or (Path(known.adapter_path).parent / "train.log"))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "mlx_lm.lora",
        *passthrough,
        "--iters", str(known.iters),
        "--adapter-path", known.adapter_path,
    ]

    print(f"command : {' '.join(cmd)}")
    print(f"log     : {log_path}")
    print(f"started : {time.strftime('%Y-%m-%d %H:%M:%S')}\n", flush=True)

    val_history: list[tuple[int, float]] = []
    last_iter = 0
    started = time.time()

    bar = tqdm(
        total=known.iters,
        unit="iter",
        dynamic_ncols=True,
        smoothing=0.05,
        desc="training",
    )

    # stderr folded into stdout so a traceback lands in the log too.
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        with log_path.open("w", encoding="utf-8") as log:
            assert process.stdout is not None
            for raw in process.stdout:
                log.write(raw)
                log.flush()
                line = raw.rstrip()

                iter_match = ITER_RE.search(line)
                if iter_match:
                    current = int(iter_match.group(1))
                    if current > last_iter:
                        bar.update(current - last_iter)
                        last_iter = current

                postfix = {}
                train_loss = TRAIN_LOSS_RE.search(line)
                if train_loss:
                    postfix["train"] = train_loss.group(1)
                val_loss = VAL_LOSS_RE.search(line)
                if val_loss:
                    value = float(val_loss.group(1))
                    postfix["val"] = f"{value:.4f}"
                    if iter_match:
                        val_history.append((int(iter_match.group(1)), value))
                        best_iter, best = min(val_history, key=lambda p: p[1])
                        postfix["best_val"] = f"{best:.4f}@{best_iter}"
                        if value > best:
                            # The signal you cannot watch while asleep.
                            bar.write(
                                f"  [watch] val loss {value:.4f} is above the best "
                                f"{best:.4f} from iter {best_iter} -- possible overfitting"
                            )
                tokens_sec = TOKENS_SEC_RE.search(line)
                if tokens_sec:
                    postfix["tok/s"] = tokens_sec.group(1)
                peak_mem = PEAK_MEM_RE.search(line)
                if peak_mem:
                    postfix["mem"] = f"{peak_mem.group(1)}GB"
                if postfix:
                    bar.set_postfix(postfix)

                # Anything that is not a routine report still deserves to be seen.
                if not iter_match and line.strip():
                    bar.write(f"  {line}")
    except KeyboardInterrupt:
        bar.write("\ninterrupted -- terminating mlx_lm.lora")
        process.terminate()
        process.wait(timeout=30)
    finally:
        bar.close()

    code = process.wait()
    elapsed = time.time() - started

    print(f"\nfinished: {time.strftime('%Y-%m-%d %H:%M:%S')}  ({elapsed / 3600:.2f} h)")
    print(f"exit code: {code}")
    print(f"log      : {log_path}")

    if val_history:
        best_iter, best = min(val_history, key=lambda p: p[1])
        final_iter, final = val_history[-1]
        print(f"\nvalidation loss: {len(val_history)} evaluations")
        print(f"  best  {best:.4f} at iter {best_iter}")
        print(f"  final {final:.4f} at iter {final_iter}")
        if final > best * 1.02 and final_iter > best_iter:
            print(
                f"\n  OVERFITTING: val loss rose {100 * (final / best - 1):.1f}% after iter {best_iter}.\n"
                f"  The checkpoint near iter {best_iter} is the one to evaluate, not the final one.\n"
                f"  Re-run with --iters {best_iter} if you want a clean adapter."
            )
        else:
            print("\n  val loss did not rise materially -- the final adapter is the one to evaluate.")
    else:
        print(
            "\nno validation losses were parsed. Either --steps-per-eval was never "
            "reached, or the report format differs from the regexes in this script. "
            f"The raw loss lines are in {log_path}."
        )

    return code


if __name__ == "__main__":
    sys.exit(main())

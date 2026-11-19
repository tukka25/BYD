#!/usr/bin/env python3
"""Read a finished mlx_lm.lora log and report the validation-loss trajectory.

mlx-lm 0.32.2 already renders a progress bar and prints each loss as it goes
(mlx_lm/cli_ui.py: TrainUI). What it does not do is summarise the run: it never
tells you which iteration validation loss bottomed out at, or whether it rose
afterwards. That is the overfitting signal, and it is exactly the thing you
cannot watch while asleep.

This parses the log after the fact rather than wrapping training, so it cannot
interfere with the run and a parsing failure costs nothing.

    .venv/bin/python summarize_run.py runs/lora-v1/train.log
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# Formats from mlx_lm/cli_ui.py, with rich markup resolved:
#   train: "  {it:>4}    {loss:>5.3f} ▼    {tok/s:>5,.0f}    {tokens:>5.1f}k"
#   val:   "  {it:>4}    val {loss:>5.3f}    {secs:.2f}s"
VAL = re.compile(r"^\s*(\d+)\s+val\s+([0-9]*\.?[0-9]+)")
TRAIN = re.compile(r"^\s*(\d+)\s+([0-9]*\.?[0-9]+)\s*[▼▲]?\s+([\d,]+)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", nargs="?", default="runs/lora-v1/train.log")
    args = parser.parse_args()

    path = Path(args.log)
    if not path.is_file():
        print(f"no log at {path}")
        return 1

    train: list[tuple[int, float]] = []
    val: list[tuple[int, float]] = []
    saves: list[str] = []

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = ANSI.sub("", raw)
        m = VAL.match(line)
        if m:
            val.append((int(m.group(1)), float(m.group(2))))
            continue
        if line.strip().startswith("save"):
            saves.append(line.strip())
            continue
        m = TRAIN.match(line)
        if m:
            train.append((int(m.group(1)), float(m.group(2))))

    print(f"log: {path}")
    print(f"  train reports : {len(train)}")
    print(f"  val reports   : {len(val)}")
    print(f"  checkpoints   : {len(saves)}")

    if not train and not val:
        print(
            "\nNothing parsed. mlx-lm's report format may have changed, or the run\n"
            "died before its first report. The raw log is intact -- read it directly."
        )
        return 1

    if train:
        first_it, first_loss = train[0]
        last_it, last_loss = train[-1]
        print(f"\ntrain loss: {first_loss:.4f} @ iter {first_it}  ->  {last_loss:.4f} @ iter {last_it}")

    if not val:
        print(
            "\nNo validation losses. Either --steps-per-eval was never reached or\n"
            "no valid set was given, so the overfitting question is unanswerable."
        )
        return 0

    best_it, best = min(val, key=lambda p: p[1])
    final_it, final = val[-1]
    print(f"\nval loss: {len(val)} evaluations")
    print(f"  first  {val[0][1]:.4f} @ iter {val[0][0]}")
    print(f"  best   {best:.4f} @ iter {best_it}")
    print(f"  final  {final:.4f} @ iter {final_it}")

    rise = (final / best - 1) * 100 if best else 0.0
    if final_it > best_it and rise > 2:
        print(
            f"\n  OVERFITTING: val loss rose {rise:.1f}% after iter {best_it}.\n"
            f"  Evaluate the checkpoint nearest iter {best_it}, not the final adapter.\n"
            f"  To get a clean adapter, re-run with --iters {best_it}."
        )
    elif final_it > best_it:
        print(f"\n  val loss drifted up {rise:.1f}% after iter {best_it} -- within noise.")
    else:
        print("\n  val loss was still at its minimum at the end: the final adapter is the one to evaluate.")
        print("  It may be worth training longer.")

    print("\n  val trajectory:")
    for it, loss in val:
        mark = "  <- best" if it == best_it else ""
        print(f"    iter {it:>5}  {loss:.4f}{mark}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

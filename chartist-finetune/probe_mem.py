#!/usr/bin/env python3
"""Measure peak GPU memory for one LoRA training step at a given sequence length.

Replicates what mlx_lm.lora does -- load, wrap in LoRA, optional grad checkpoint,
then one value_and_grad on a synthetic batch -- and reports mx.get_peak_memory().
Purpose is to turn "it OOMs" into a slope and an intercept, so the RAM actually
needed for a given --max-seq-length is a number rather than a guess.
"""
import argparse, gc, sys
import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten
from mlx_lm import load
from mlx_lm.tuner.utils import linear_to_lora_layers
from mlx_lm.tuner.trainer import default_loss, grad_checkpoint

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="models/qwen3.5-9b-4bit")
ap.add_argument("--lengths", default="512,768,1024,1280,1536")
ap.add_argument("--num-layers", type=int, default=16)
ap.add_argument("--checkpoint", action="store_true")
ap.add_argument("--batch-size", type=int, default=1)
args = ap.parse_args()

model, tok = load(args.model)
model.freeze()
linear_to_lora_layers(model, args.num_layers, {"rank": 8, "scale": 20.0, "dropout": 0.0})
if args.checkpoint:
    grad_checkpoint(model.layers[0])
model.train()
nparam = sum(v.size for _, v in tree_flatten(model.trainable_parameters()))
mx.eval(model.parameters())
base = mx.get_peak_memory() / 1024**3
print(f"model loaded: trainable {nparam/1e6:.2f}M | weights resident ~{mx.get_active_memory()/1024**3:.2f} GB")
print(f"checkpoint={args.checkpoint} num_layers={args.num_layers} batch={args.batch_size}\n")
print(f"{'seq':>6} {'peak GB':>9} {'delta vs weights':>18} {'MB/token':>10}")
print("-" * 50)

loss_vg = nn.value_and_grad(model, default_loss)
for L in [int(x) for x in args.lengths.split(",")]:
    mx.clear_cache()
    mx.reset_peak_memory()
    batch = mx.ones((args.batch_size, L + 1), dtype=mx.int32)
    # offset 0 so every token counts, as a worst case for the loss mask
    lengths = mx.array([[0, L]] * args.batch_size)
    try:
        (lv, toks), grad = loss_vg(model, batch, lengths)
        mx.eval(lv, toks, grad)
        peak = mx.get_peak_memory() / 1024**3
        act = mx.get_active_memory() / 1024**3
        print(f"{L:>6} {peak:>9.2f} {peak-act:>18.2f} {(peak-act)*1024/L:>10.2f}")
    except Exception as e:
        print(f"{L:>6}    OOM/err: {str(e)[:70]}")
        break
    del grad
    gc.collect()

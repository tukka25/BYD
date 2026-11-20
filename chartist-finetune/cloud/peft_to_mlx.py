#!/usr/bin/env python3
"""Convert a PEFT (HuggingFace) LoRA adapter into mlx-lm's adapter format.

Needed because mlx-lm loads only adapters it produced itself: `load_adapters`
reads `adapters.safetensors` with its own key names, and there is no official
PEFT importer. Training happened on CUDA with peft, so the adapter has to be
translated to be served locally on Apple silicon.

The mapping, each part verified against the installed mlx-lm rather than assumed:

  key    base_model.model.model.layers.N.<mod>.lora_A.weight
      -> language_model.model.layers.N.<mod>.lora_a
         (strip "base_model.model.", prepend "language_model.", lower-case the
         A/B and drop ".weight")

  shape  peft lora_A is (r, in_features)  -> mlx lora_a is (in_features, r)
         peft lora_B is (out_features, r) -> mlx lora_b is (r, out_features)
         Both are a plain transpose. mlx computes
             y + scale * ((x @ lora_a) @ lora_b)      [tuner/lora.py]
         and peft computes
             y + (alpha/r) * (x @ A.T @ B.T)
         so lora_a = A.T, lora_b = B.T and scale = alpha / r.

  scale  peft alpha 32 / r 16 -> mlx scale 2.0. mlx-lm's own default is 20.0, so
         leaving it unset would scale the update 10x and wreck the model.

num_layers is written as 32 (every layer), because the adapter covers MLP on all
32 layers while attention exists on only the 8 full-attention ones. mlx's
linear_to_lora_layers also wraps the 24 linear_attn layers, which this adapter
deliberately never trained; those stay at their initialisation, and since mlx
inits lora_b to ZEROS an unloaded adapter is an exact identity, so they are
harmless no-ops rather than random noise.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import mlx.core as mx
import numpy as np
from safetensors.numpy import load_file

PEFT_KEY = re.compile(r"^base_model\.model\.(?P<path>model\.layers\.\d+\..+)\.lora_(?P<ab>[AB])\.weight$")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--peft", default="cloud/artifacts/out-min", help="dir with adapter_model.safetensors + adapter_config.json")
    ap.add_argument("--out", default="runs/adapters-mlx")
    ap.add_argument("--num-layers", type=int, default=32)
    args = ap.parse_args()

    peft_dir = Path(args.peft)
    cfg = json.loads((peft_dir / "adapter_config.json").read_text(encoding="utf-8"))
    rank, alpha = int(cfg["r"]), float(cfg["lora_alpha"])
    scale = alpha / rank
    print(f"peft adapter: r={rank} alpha={alpha} -> mlx scale={scale}")
    print(f"targets: {sorted(cfg['target_modules'])}")

    tensors = load_file(peft_dir / "adapter_model.safetensors")
    out: dict[str, mx.array] = {}
    unmapped: list[str] = []
    for key, value in tensors.items():
        m = PEFT_KEY.match(key)
        if not m:
            unmapped.append(key)
            continue
        leaf = "lora_a" if m.group("ab") == "A" else "lora_b"
        new_key = f"language_model.{m.group('path')}.{leaf}"
        # Both directions are a plain transpose; see the module docstring.
        out[new_key] = mx.array(np.ascontiguousarray(value.T.astype(np.float32)))

    if unmapped:
        raise SystemExit(f"{len(unmapped)} key(s) did not match the PEFT pattern, e.g. {unmapped[:3]}")
    if any("linear_attn" in k for k in out):
        raise SystemExit("converted adapter contains linear_attn weights -- it should not")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(str(out_dir / "adapters.safetensors"), out)
    (out_dir / "adapter_config.json").write_text(
        json.dumps(
            {
                "fine_tune_type": "lora",
                "num_layers": args.num_layers,
                "lora_parameters": {"rank": rank, "scale": scale, "dropout": 0.0},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    a = sum(1 for k in out if k.endswith("lora_a"))
    b = sum(1 for k in out if k.endswith("lora_b"))
    print(f"wrote {out_dir}: {len(out)} tensors ({a} lora_a + {b} lora_b)")
    print(f"  num_layers={args.num_layers} rank={rank} scale={scale}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""LoRA fine-tune Qwen3.5-9B for the BYD chartist, on a CUDA GPU.

Run on a Runpod pod (see cloud/README.md). Writes the adapter to OUT.

Two decisions here are not defaults, and both are load-bearing.

1. `target_modules` is explicit and deliberately EXCLUDES the linear-attention
   projections. Qwen3.5 is hybrid: 24 of its 32 layers are Gated DeltaNet linear
   attention, whose forget gate (`in_proj_a`) and delta step size (`in_proj_b`)
   multiply the recurrent state at EVERY timestep. A low-rank bias on them
   therefore compounds along the sequence rather than averaging out -- a 0.5%
   shift in the per-step gate changes long-range retention by ~155x over 1,000
   tokens, and the reported symptom is looping output. `all-linear`, the usual
   best-quality setting on a dense transformer, would adapt exactly those gates.
   The script asserts afterwards that none were matched, because a silent match
   is the failure this configuration exists to prevent.

2. The prompt/answer split is done on TEXT, not on token counts. Qwen3.5 is a
   thinking model: its template ends a generation prompt with "<think>\n" and
   renders a full turn as "<think>\n\n</think>\n\n<content>", and the tokeniser
   merges the newlines across that join differently. Masking the first
   len(prompt_ids) tokens therefore lands one token off and would teach the model
   to emit "</think>" without the newlines it must produce at inference.

3. Over-length rows are DROPPED, never truncated. The tail of every row is
   `print(fig.to_json())`, the one line the chartist contract requires, so a
   truncated row teaches the model to omit it. (On mlx-lm, truncation was worse
   still: it produced an empty loss mask and a nan that poisoned the whole run.)
   The dataset is pre-capped, so this should drop zero rows -- it is a tripwire.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import torch
from torch.utils.data import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, Trainer, TrainingArguments
from peft import LoraConfig, get_peft_model

BASE = os.environ.get("BASE", "Qwen/Qwen3.5-9B")
DATA = Path(os.environ.get("DATA", "/workspace/chartist/data/mlx_1536"))
OUT = os.environ.get("OUT", "/workspace/outputs/lora-v1")
MAXLEN = int(os.environ.get("MAXLEN", "1536"))
EPOCHS = float(os.environ.get("EPOCHS", "2"))
BATCH = int(os.environ.get("BATCH", "4"))
ACCUM = int(os.environ.get("ACCUM", "2"))
LR = float(os.environ.get("LR", "2e-4"))
RANK = int(os.environ.get("RANK", "16"))
# transformers 5.23 removed warmup_ratio; only warmup_steps exists.
WARMUP = int(os.environ.get("WARMUP", "15"))
# How often to measure validation loss and keep a checkpoint. lora-v1 used
# 60/120 on 260 validation rows; v2 has 949, so it measures less often.
EVAL_STEPS = int(os.environ.get("EVAL_STEPS", "60"))
SAVE_STEPS = int(os.environ.get("SAVE_STEPS", "120"))

# Attention and MLP only. See the module docstring for why linear_attn is absent.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]

tokenizer = AutoTokenizer.from_pretrained(BASE)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token


def chat_text(messages: list[dict], add_generation_prompt: bool) -> str:
    """Render a chat with the model's own template, as text."""
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=add_generation_prompt
    )


def encode(text: str) -> list[int]:
    """Encode template-rendered text.

    add_special_tokens=False because the chat template already inserts them.
    Deliberately NOT apply_chat_template(tokenize=True): in transformers 5.x that
    returns a BatchEncoding, which extends UserDict and so is NOT an instance of
    dict -- an `isinstance(out, dict)` guard misses it and `list(out)` silently
    yields the KEYS, ['input_ids', 'attention_mask']. Every row then looks two
    tokens long and gets fully masked.
    """
    return list(tokenizer(text, add_special_tokens=False)["input_ids"])


class PromptMaskedRows(Dataset):
    """SFT rows whose loss is computed on the assistant turn only.

    The system contract and the schema block are always supplied at inference, so
    training on them spends capacity learning to emit prompts instead of code.
    """

    def __init__(self, path: Path, maxlen: int):
        self.items: list[dict] = []
        self.dropped_long = 0
        self.dropped_empty = 0
        self.prefix_mismatch = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            messages = json.loads(line)["messages"]
            full_text = chat_text(messages, add_generation_prompt=False)
            prompt_text = chat_text(messages[:-1], add_generation_prompt=True)
            if not full_text.startswith(prompt_text):
                # Measured to hold for all 1926 train + 259 valid rows. If it
                # ever stops holding, the mask boundary is unknown, so skip the
                # row rather than train on a guessed boundary.
                self.prefix_mismatch += 1
                continue
            # Split on TEXT, then tokenise the halves separately, so the mask
            # boundary is exact by construction. Tokenising the whole string and
            # masking the first len(prompt) ids is off by a token here: Qwen3.5's
            # template ends a generation prompt with "<think>\n" while the full
            # render continues "\n</think>\n\n", and the tokeniser merges those
            # newlines differently across that join. Masking by length would
            # train the model to emit "</think>" without the leading newlines it
            # must actually produce at inference.
            prompt_ids = encode(prompt_text)
            answer_ids = encode(full_text[len(prompt_text):])
            if not answer_ids:
                self.dropped_empty += 1
                continue
            if len(prompt_ids) + len(answer_ids) > maxlen:
                self.dropped_long += 1
                continue
            self.items.append(
                {
                    "input_ids": prompt_ids + answer_ids,
                    "labels": [-100] * len(prompt_ids) + answer_ids,
                }
            )

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int) -> dict:
        return self.items[i]


def collate(batch: list[dict]) -> dict:
    width = max(len(b["input_ids"]) for b in batch)
    pad = tokenizer.pad_token_id
    input_ids, labels, attention = [], [], []
    for b in batch:
        gap = width - len(b["input_ids"])
        input_ids.append(b["input_ids"] + [pad] * gap)
        labels.append(b["labels"] + [-100] * gap)
        attention.append([1] * len(b["input_ids"]) + [0] * gap)
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.tensor(attention, dtype=torch.long),
    }


def main() -> int:
    train = PromptMaskedRows(DATA / "train.jsonl", MAXLEN)
    valid = PromptMaskedRows(DATA / "valid.jsonl", MAXLEN)
    print(
        f"train {len(train)} / valid {len(valid)} | "
        f"dropped over {MAXLEN} tokens: {train.dropped_long}+{valid.dropped_long} | "
        f"dropped for an empty label mask: {train.dropped_empty}+{valid.dropped_empty} | "
        f"prefix mismatches: {train.prefix_mismatch}+{valid.prefix_mismatch}",
        flush=True,
    )
    # Fail here, before the 6-minute model load, rather than after it. The first
    # run spent that load and then died on an empty dataset.
    if not len(train) or not len(valid):
        sys.exit(
            "REFUSING TO TRAIN: a split tokenised to zero usable rows. "
            "dropped_long means MAXLEN is below the cap the data was built at; "
            "dropped_empty means prompt masking consumed every label, i.e. the "
            "tokeniser returned something other than a flat list of ids."
        )
    if train.dropped_long or valid.dropped_long:
        print("  NOTE the dataset is pre-capped by cap_dataset.py, so a non-zero "
              "over-length count means MAXLEN here is below that cap.", flush=True)

    model = AutoModelForCausalLM.from_pretrained(BASE, dtype=torch.bfloat16, device_map="cuda")
    model.config.use_cache = False
    model = get_peft_model(
        model,
        LoraConfig(
            r=RANK,
            lora_alpha=2 * RANK,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=TARGET_MODULES,
        ),
    )

    adapted = [n for n, _ in model.named_modules() if n.endswith("lora_A.default")]
    gated = [n for n in adapted if "linear_attn" in n]
    print(f"LoRA adapters on {len(adapted)} modules; linear_attn among them: {len(gated)}", flush=True)
    if gated:
        sys.exit("REFUSING TO TRAIN: LoRA matched linear-attention modules: " + ", ".join(gated[:6]))
    if not adapted:
        sys.exit("REFUSING TO TRAIN: target_modules matched nothing -- check the module names.")
    model.print_trainable_parameters()

    trainer = Trainer(
        model=model,
        args=TrainingArguments(
            output_dir=OUT,
            num_train_epochs=EPOCHS,
            per_device_train_batch_size=BATCH,
            gradient_accumulation_steps=ACCUM,
            learning_rate=LR,
            lr_scheduler_type="cosine",
            warmup_steps=WARMUP,
            bf16=True,
            gradient_checkpointing=True,
            gradient_checkpointing_kwargs={"use_reentrant": False},
            logging_steps=10,
            eval_strategy="steps",
            eval_steps=EVAL_STEPS,
            save_strategy="steps",
            save_steps=SAVE_STEPS,
            save_total_limit=3,
            # The adapter saved at the end is the checkpoint with the lowest
            # validation loss, so a second epoch that starts to overfit cannot
            # ship worse than the earlier checkpoint it overfit from.
            load_best_model_at_end=True,
            metric_for_best_model="eval_loss",
            greater_is_better=False,
            report_to=[],
            seed=42,
            max_grad_norm=1.0,
        ),
        train_dataset=train,
        eval_dataset=valid,
        data_collator=collate,
    )
    trainer.train()
    model.save_pretrained(OUT)
    tokenizer.save_pretrained(OUT)
    print("TRAIN_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

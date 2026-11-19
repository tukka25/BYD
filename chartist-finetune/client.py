"""Anthropic client, batch runner, and cost accounting.

The key lives in <repo>/.env as CLAUDE_API_KEY, which the SDK does not resolve
on its own, so it is read here and passed explicitly. Never printed.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import anthropic
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".env"

SONNET = "claude-sonnet-5-5"
HAIKU = "claude-haiku-5-5"

PRICES = {  # USD per 1M tokens: (input, output, cache_read)
    SONNET: (2.00, 10.00, 0.10),
    HAIKU: (0.10, 0.50, 0.01),
}


def _read_key() -> str:
    if not ENV_FILE.is_file():
        raise RuntimeError(f"{ENV_FILE} not found")
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        if name.strip() in {"CLAUDE_API_KEY", "ANTHROPIC_API_KEY"}:
            cleaned = value.strip().strip('"').strip("'")
            if cleaned:
                return cleaned
    raise RuntimeError("CLAUDE_API_KEY not set in .env")


def get_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=_read_key())


def cached_system(text: str) -> list[dict]:
    """System block with a cache breakpoint. All requests in a batch share it."""
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def json_request(
    custom_id: str,
    model: str,
    system: str,
    user: str,
    schema: dict,
    max_tokens: int,
    effort: str = "low",
) -> Request:
    return Request(
        custom_id=custom_id,
        params=MessageCreateParamsNonStreaming(
            model=model,
            max_tokens=max_tokens,
            system=cached_system(system),
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": user}],
        ),
    )


@dataclass
class BatchOutcome:
    batch_id: str
    payloads: dict[str, dict] = field(default_factory=dict)
    usage: dict = field(default_factory=lambda: {"input": 0, "output": 0, "cache_read": 0})
    refusals: int = 0
    errored: int = 0
    unparsed: int = 0


def run_batch(requests: list, label: str, poll_seconds: int = 30) -> BatchOutcome:
    """Submit, poll to completion, collect structured payloads keyed by custom_id."""
    client = get_client()
    batch = client.messages.batches.create(requests=requests)
    print(f"[{label}] batch {batch.id}: {len(requests)} requests", flush=True)

    while True:
        batch = client.messages.batches.retrieve(batch.id)
        if batch.processing_status == "ended":
            break
        print(
            f"[{label}] {batch.processing_status} "
            f"processing={batch.request_counts.processing} "
            f"succeeded={batch.request_counts.succeeded}",
            flush=True,
        )
        time.sleep(poll_seconds)

    outcome = BatchOutcome(batch_id=batch.id)
    outcome.errored = batch.request_counts.errored

    for result in client.messages.batches.results(batch.id):
        if result.result.type != "succeeded":
            continue
        message = result.result.message
        outcome.usage["input"] += message.usage.input_tokens
        outcome.usage["output"] += message.usage.output_tokens
        outcome.usage["cache_read"] += (
            getattr(message.usage, "cache_read_input_tokens", 0) or 0
        )
        if message.stop_reason == "refusal":
            outcome.refusals += 1
            continue
        text = next((b.text for b in message.content if b.type == "text"), "")
        try:
            outcome.payloads[result.custom_id] = json.loads(text)
        except json.JSONDecodeError:
            outcome.unparsed += 1
    return outcome


def price(usage: dict, model: str, batched: bool = True) -> float:
    rate_in, rate_out, rate_cache = PRICES[model]
    billed_input = max(0, usage.get("input", 0) - usage.get("cache_read", 0))
    total = (
        billed_input / 1_000_000 * rate_in
        + usage.get("cache_read", 0) / 1_000_000 * rate_cache
        + usage.get("output", 0) / 1_000_000 * rate_out
    )
    return round(total * (0.5 if batched else 1.0), 4)


def record_spend(label: str, model: str, usage: dict, extra: dict | None = None) -> float:
    """Append a line to the ledger so the budget stays auditable."""
    cost = price(usage, model)
    ledger = Path("runs/spend.jsonl")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"label": label, "model": model, "usage": usage, "cost_usd": cost,
                 **(extra or {})}
            )
            + "\n"
        )
    print(f"[{label}] cost ${cost:.4f} (batched)")
    return cost

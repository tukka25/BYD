"""One place that decides which model serves which agent.

Two backends:

* ``ollama`` — the original path, Ollama's ``/api/chat`` via ``ChatOllama``.
* ``mlx``  — an OpenAI-compatible server, which is what ``mlx_lm server``
  exposes. This is how the fine-tuned chartist adapter is served on Apple
  silicon, and it is why the switch exists at all: the adapter is a LoRA over
  Qwen3.5-9B and cannot be loaded by Ollama.

Three roles, because they want different things from a model:

* ``chartist``  — writes Plotly code. This is the ONLY role the fine-tune
  covers, so under the mlx backend it may point at a different server than the
  others (``MLX_CHARTIST_BASE_URL``). Greedy decoding, because two runs of the
  same request should agree.
* ``planner``   — emits one small JSON object. Greedy.
* ``detective`` — ranks candidate data sources. Greedy, and deliberately NOT a
  tool-calling role any more; see data_detective.py.

A single ``mlx_lm server`` hosts one adapter at a time, so serving the
fine-tuned chartist and the base model simultaneously means two servers. Pointing
every role at one server is also fine and uses half the memory — the adapter is
a mild bias toward Plotly code, not a different model.
"""
from __future__ import annotations

import logging
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel

from app.core.config import get_settings
from app.services.agents.chartist_contract import CHARTIST_MAX_TOKENS
from app.services.agents.planning_contract import ANALYST_MAX_TOKENS, PLANNER_MAX_TOKENS

logger = logging.getLogger(__name__)

Role = Literal["planner", "chartist", "detective", "narrator", "analyst", "spec_planner"]

# Greedy everywhere. These agents are infrastructure, not chat: the same
# question should produce the same chart.
_TEMPERATURE = 0.0
# A title is one short line; anything longer is the model talking to itself.
_MAX_TOKENS = {
    "planner": 256,
    # Shared with the eval and the A/B harness, so they score what the app runs.
    "chartist": CHARTIST_MAX_TOKENS,
    "detective": 512,
    "narrator": 128,
    # The dashboard's planning calls write whole JSON plans; shared with the
    # planning eval through planning_contract.
    "analyst": ANALYST_MAX_TOKENS,
    "spec_planner": PLANNER_MAX_TOKENS,
}
# The dashboard's planning calls answer in JSON with thinking switched off, per
# request (mlx_lm server reads chat_template_kwargs). On base weights with
# thinking on, Qwen3.5 opens with a reasoning essay and never reaches the JSON
# inside the cap (measured for the planner, data/role_measure.json), and the
# adapter was trained on answers that follow a closed think block, which is
# exactly what this prompt ends with. measure_planning.py sends the same flag.
_NO_THINKING = {"analyst", "spec_planner"}
_JSON_ROLES = {"planner", "analyst", "spec_planner"}


def _ollama(role: Role) -> BaseChatModel:
    from app.services.qwen_slm import LocalQwenChatModel

    settings = get_settings()
    # Ollama can constrain output to JSON server-side; only the planner wants it.
    return LocalQwenChatModel(
        model=settings.OLLAMA_MODEL,
        temperature=_TEMPERATURE,
        format="json" if role in _JSON_ROLES else "",
    )


def _mlx(role: Role) -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    settings = get_settings()
    base_url = settings.chartist_base_url if role == "chartist" else settings.MLX_BASE_URL
    model = settings.chartist_model if role == "chartist" else settings.MLX_MODEL
    # No response_format here: mlx_lm server does not advertise JSON mode, so the
    # planner carries its schema in the prompt and parses leniently instead.
    extra = (
        {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
        if role in _NO_THINKING
        else {}
    )
    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=settings.MLX_API_KEY,
        temperature=_TEMPERATURE,
        max_tokens=_MAX_TOKENS[role],
        timeout=settings.MLX_TIMEOUT_SECONDS,
        **extra,
    )


def get_llm(role: Role) -> BaseChatModel:
    """Return the chat model for a role, per ``LLM_BACKEND``."""
    settings = get_settings()
    backend = (settings.LLM_BACKEND or "ollama").strip().lower()
    if backend == "mlx":
        llm = _mlx(role)
        logger.info(
            "[llm] role=%s backend=mlx model=%s url=%s",
            role,
            settings.chartist_model if role == "chartist" else settings.MLX_MODEL,
            settings.chartist_base_url if role == "chartist" else settings.MLX_BASE_URL,
        )
        return llm
    if backend != "ollama":
        # Fail loudly rather than silently serving a model nobody asked for.
        raise ValueError(f"LLM_BACKEND must be 'ollama' or 'mlx', got {backend!r}")
    logger.info("[llm] role=%s backend=ollama model=%s", role, settings.OLLAMA_MODEL)
    return _ollama(role)

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

from openai import OpenAI


@dataclass
class LLMSettings:
    rephrase_model: str
    answer_aug_model: str
    fallback_model: str
    temperature_rephrase: float
    temperature_answer_aug: float
    max_tokens_rephrase: int
    max_tokens_answer_aug: int
    max_generation_retries: int


class LLMClient:
    def __init__(self, settings: LLMSettings, request_gate: Callable[[], None] | None = None) -> None:
        self.settings = settings
        self.request_gate = request_gate
        self._local = threading.local()

    def _get_client(self) -> OpenAI:
        # OpenAI client per thread for safer concurrent usage.
        client = getattr(self._local, "client", None)
        if client is None:
            client = OpenAI()
            self._local.client = client
        return client

    def _chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if self.request_gate is not None:
            self.request_gate()
        response = self._get_client().chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    def _with_retries(self, fn) -> str:
        last_error: Optional[Exception] = None
        for attempt in range(self.settings.max_generation_retries):
            try:
                return fn()
            except Exception as e:  # noqa: BLE001
                last_error = e
                time.sleep(1.2 * (attempt + 1))
        if last_error is None:
            raise RuntimeError("Unknown LLM failure")
        raise RuntimeError(f"LLM call failed after retries: {last_error}")

    def generate_rephrase(self, system_prompt: str, user_prompt: str) -> str:
        text = self._with_retries(
            lambda: self._chat(
                model=self.settings.rephrase_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=self.settings.temperature_rephrase,
                max_tokens=self.settings.max_tokens_rephrase,
            )
        )

        # Expecting a tiny JSON object; fallback to model retry if parse fails.
        try:
            obj = json.loads(text)
            value = obj.get("rephrased_user", "")
            if isinstance(value, str) and value.strip():
                return value.strip()
        except Exception:  # noqa: BLE001
            pass

        fallback = self._with_retries(
            lambda: self._chat(
                model=self.settings.fallback_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=self.settings.temperature_rephrase,
                max_tokens=self.settings.max_tokens_rephrase,
            )
        )
        obj = json.loads(fallback)
        return str(obj["rephrased_user"]).strip()

    def generate_answer_aug(self, system_prompt: str, user_prompt: str) -> str:
        try:
            return self._with_retries(
                lambda: self._chat(
                    model=self.settings.answer_aug_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=self.settings.temperature_answer_aug,
                    max_tokens=self.settings.max_tokens_answer_aug,
                )
            )
        except Exception:
            return self._with_retries(
                lambda: self._chat(
                    model=self.settings.fallback_model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=self.settings.temperature_answer_aug,
                    max_tokens=self.settings.max_tokens_answer_aug,
                )
            )

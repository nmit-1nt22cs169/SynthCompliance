"""Generic OpenAI-compatible LLM provider — hosted (cloud) or self-hosted (NIM/Ollama)."""

from __future__ import annotations

import json
import os
from typing import Any

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None  # type: ignore


def _bool_env(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


class LLMProvider:
    """
    Dual-mode OpenAI-compatible client, generic across vendors — works identically against
    NVIDIA's Build API, a self-hosted NIM box, or local Ollama (which serves an OpenAI-compatible
    API and can host multiple models at once, selected per-request via `model`, not `base_url`).

    USE_SELF_HOSTED=true → LOCAL_BASE_URL/LOCAL_API_KEY/LOCAL_LLM_MODEL
    else                 → PRIVATE_BASE_URL/PRIVATE_API_KEY/HOSTED_LLM_MODEL

    `prefix` lets a second model slot (e.g. a retrain-target model) reuse this same class under
    its own env var namespace (e.g. "RETRAIN_"). `fallback`, only ever passed for that second
    slot, supplies defaults for anything left unset — most retrain models are served from the
    exact same place as the generation model, so only the model name usually needs to differ.
    """

    def __init__(self, prefix: str = "", fallback: "LLMProvider | None" = None) -> None:
        # Blank counts the same as unset, not just a literally-missing var — docker-compose's
        # `${VAR:-}` substitution always sets the container env var, empty string when the host
        # left it blank, so `is not None` alone would never fall through to the inherited value.
        use_self_hosted_raw = os.getenv(f"{prefix}USE_SELF_HOSTED", "")
        if use_self_hosted_raw.strip():
            self.use_self_hosted = _bool_env(f"{prefix}USE_SELF_HOSTED", False)
        else:
            self.use_self_hosted = fallback.use_self_hosted if fallback else False

        if self.use_self_hosted:
            self.base_url = os.getenv(f"{prefix}LOCAL_BASE_URL") or (
                fallback.base_url if fallback else "http://localhost:11434/v1"
            )
            self.api_key = os.getenv(f"{prefix}LOCAL_API_KEY") or (
                fallback.api_key if fallback else "not-needed"
            )
            self.model = os.getenv(f"{prefix}LOCAL_LLM_MODEL", "")
        else:
            self.base_url = os.getenv(f"{prefix}PRIVATE_BASE_URL") or (
                fallback.base_url if fallback else "https://integrate.api.nvidia.com/v1"
            )
            self.api_key = os.getenv(f"{prefix}PRIVATE_API_KEY") or (
                fallback.api_key if fallback else ""
            )
            self.model = os.getenv(f"{prefix}HOSTED_LLM_MODEL", "")

        if not self.model:
            self.model = fallback.model if fallback else "nvidia/nemotron-3-super"

        self._client = None
        if OpenAI is not None and (self.api_key or self.use_self_hosted):
            try:
                self._client = OpenAI(base_url=self.base_url, api_key=self.api_key or "not-needed")
            except Exception:
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None and bool(self.api_key or self.use_self_hosted)

    def complete_json(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.4,
        max_tokens: int = 2048,
    ) -> dict[str, Any] | list[Any] | None:
        """Ask for JSON; returns parsed object or None on failure / offline."""
        if not self.available or self._client is None:
            return None
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content or "{}"
            return json.loads(text)
        except Exception:
            return None


_provider: LLMProvider | None = None
_retrain_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = LLMProvider()
    return _provider


def get_retrain_provider() -> LLMProvider:
    """The second model slot for the (future) retrain-target/Copilot path — any LLM, not tied to
    a specific one. Gated by RETRAIN_MODEL elsewhere, not by this function. Defaults to the same
    base_url/api_key/self-hosted mode as the primary provider unless RETRAIN_* vars explicitly
    override them."""
    global _retrain_provider
    if _retrain_provider is None:
        _retrain_provider = LLMProvider(prefix="RETRAIN_", fallback=get_provider())
    return _retrain_provider

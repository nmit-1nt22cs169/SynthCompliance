"""Nemotron provider abstraction — NVIDIA Build API or self-hosted NIM."""

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


class NemotronProvider:
    """
    Dual-mode OpenAI-compatible client.
    USE_SELF_HOSTED=true → NIM_BASE_URL (GPU cluster)
    else → https://integrate.api.nvidia.com/v1
    """

    def __init__(self) -> None:
        self.use_self_hosted = _bool_env("USE_SELF_HOSTED", False)
        if self.use_self_hosted:
            self.base_url = os.getenv("NIM_BASE_URL", "http://localhost:8000/v1")
            self.api_key = os.getenv("NIM_API_KEY", "not-needed")
        else:
            self.base_url = os.getenv(
                "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
            )
            self.api_key = os.getenv("NVIDIA_API_KEY", "")
        self.model = os.getenv("NEMOTRON_MODEL", "nvidia/nemotron-3-super")
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


_provider: NemotronProvider | None = None


def get_provider() -> NemotronProvider:
    global _provider
    if _provider is None:
        _provider = NemotronProvider()
    return _provider

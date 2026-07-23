"""Prompt catalog loading utilities."""

from __future__ import annotations

import json
from collections.abc import ItemsView, Mapping
from pathlib import Path

from .config import Settings

DEFAULT_PROMPT_FILE = Path(__file__).with_name("data") / "tool_prompts.json"


class PromptCatalog:
    """In-memory store for tool prompts."""

    def __init__(self, prompts: Mapping[str, str]) -> None:
        self._prompts: dict[str, str] = {name: text for name, text in prompts.items() if text}

    def get(self, tool_name: str) -> str | None:
        """Return the prompt configured for ``tool_name`` if any."""

        return self._prompts.get(tool_name)

    def descriptors(self) -> dict[str, str]:
        """Expose the raw prompt mapping."""

        return dict(self._prompts)

    def items(self) -> ItemsView[str, str]:
        """Return an iterator over ``(tool, prompt)`` pairs."""

        return self._prompts.items()


def load_catalog(settings: Settings) -> PromptCatalog:
    """Load the prompt catalog referenced by ``settings``."""

    candidate_path = getattr(settings, "prompt_catalog_path", None) or DEFAULT_PROMPT_FILE
    try:
        raw = candidate_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return PromptCatalog({})
    data = json.loads(raw)
    prompts = data.get("tools", {}) if isinstance(data, dict) else {}
    if not isinstance(prompts, dict):
        prompts = {}
    filtered: dict[str, str] = {}
    for key, value in prompts.items():
        if isinstance(key, str) and isinstance(value, str):
            filtered[key] = value.strip()
    return PromptCatalog(filtered)

from __future__ import annotations

import json
from typing import Any


class UIExtractor:
    """Flatten accessibility node text fields into a plain string."""

    TEXT_KEYS = (
        "text",
        "content-desc",
        "content_description",
        "label",
        "hint",
        "value",
        "description",
        "name",
    )
    CHILD_KEYS = ("nodes", "children")

    def extract(self, node_dump: dict | list | str | None) -> str:
        parsed = self._coerce(node_dump)
        chunks: list[str] = []
        self._collect(parsed, chunks)
        return "\n".join(chunks) if chunks else self._fallback_text(node_dump)

    def _coerce(self, node_dump: dict | list | str | None) -> Any:
        if isinstance(node_dump, (dict, list)):
            return node_dump
        if isinstance(node_dump, str):
            stripped = node_dump.strip()
            if not stripped:
                return {}
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return stripped
            return stripped
        return {}

    def _collect(self, value: Any, chunks: list[str]) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                chunks.append(text)
            return

        if isinstance(value, list):
            for item in value:
                self._collect(item, chunks)
            return

        if not isinstance(value, dict):
            return

        for key in self.TEXT_KEYS:
            candidate = value.get(key)
            if isinstance(candidate, str):
                text = candidate.strip()
                if text:
                    chunks.append(text)

        for key in self.CHILD_KEYS:
            if key in value:
                self._collect(value[key], chunks)

        for key, nested in value.items():
            if key in self.TEXT_KEYS or key in self.CHILD_KEYS:
                continue
            if isinstance(nested, (dict, list)):
                self._collect(nested, chunks)

    def _fallback_text(self, node_dump: dict | list | str | None) -> str:
        if isinstance(node_dump, str):
            return node_dump.strip()
        if node_dump is None:
            return ""
        try:
            return json.dumps(node_dump, ensure_ascii=True)
        except TypeError:
            return str(node_dump)

"""Custom socket types and payload objects carried between NInfer nodes."""

from __future__ import annotations

import json
from typing import Any

from comfy_api.latest import io

# --- Socket types -----------------------------------------------------------
ParamClient = io.Custom("NINFER_CLIENT")
ParamOptions = io.Custom("NINFER_OPTIONS")
ParamHistory = io.Custom("NINFER_HISTORY")


class OptionsPayload:
    """Accumulator for generation settings, merged node by node."""

    def __init__(self, options: dict[str, Any] | None = None) -> None:
        self.options = options

    def get_options_copy(self) -> dict[str, Any]:
        return self.options.copy() if self.options else {}

    def __str__(self) -> str:
        return json.dumps(self.options, indent=4)


class HistoryPayload:
    """Conversation state, optionally carried across calls."""

    def __init__(self, messages: list[dict[str, Any]] | None = None) -> None:
        self.messages = messages

    def get_messages_copy(self) -> list[dict[str, Any]]:
        # Deep-ish copy: message dicts are small, and `content` may be a list
        # of content parts that we must not hand out by reference.
        return [dict(m) for m in self.messages] if self.messages else []

    def __str__(self) -> str:
        return json.dumps(self.messages, indent=4)

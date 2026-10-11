"""NInfer nodes for ComfyUI.

Talks to a local NInfer server over its OpenAI-compatible API, starting and
stopping the process so it can share a 24 GiB card with ComfyUI.
"""

from typing_extensions import override

from comfy_api.latest import ComfyExtension, io

from . import lifecycle
from .chat import NinferChat
from .client import NinferClient
from .options import (
    NinferOptionExtraBody,
    NinferOptionMaxTokens,
    NinferOptionReasoningEffort,
    NinferOptionSeed,
    NinferOptionSystemPrompt,
    NinferOptionTemperature,
    NinferOptionTopK,
    NinferOptionTopP,
)
from .server import NinferServer

__all__ = ["NinferExtension", "comfy_entrypoint"]


class NinferExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [
            NinferClient,
            NinferChat,
            NinferServer,
            NinferOptionSystemPrompt,
            NinferOptionTemperature,
            NinferOptionMaxTokens,
            NinferOptionReasoningEffort,
            NinferOptionTopP,
            NinferOptionTopK,
            NinferOptionSeed,
            NinferOptionExtraBody,
        ]

    @override
    async def on_load(self) -> None:
        # The reaper is a daemon thread; it only acts once something has been
        # started, so it is safe to arm it as soon as the pack loads.
        lifecycle.start_reaper()


async def comfy_entrypoint() -> NinferExtension:
    return NinferExtension()

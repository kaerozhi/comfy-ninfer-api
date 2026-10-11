"""The NInfer server connection node."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from comfy_api.latest import io
from openai import OpenAI

from . import config
from .iotypes import ParamClient

# Cache the discovered model list so the combo box stays populated while the
# server happens to be stopped (e.g. while ComfyUI is rendering).
_CACHED_MODELS: list[str] = []
_FALLBACK_MODEL = "ninfer"


def _fetch_models(base_url: str, timeout: float = 5.0) -> list[str]:
    """`GET /v1/models` against a running server."""
    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {config.API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return []
    return [item["id"] for item in data if isinstance(item, dict) and item.get("id")]


def discover_models(base_url: str = config.BASE_URL) -> list[str]:
    """Model ids, live when possible and cached otherwise.

    The id is derived from the artifact, so it changes with the model file
    (`qwen3.8-27b` for the official build, a long Huihui name for IQ3_S).
    Reading it live is what keeps the pack working across artifacts.
    """
    global _CACHED_MODELS
    found = _fetch_models(base_url)
    if found:
        _CACHED_MODELS = found
        return found
    if _CACHED_MODELS:
        return _CACHED_MODELS
    return [_FALLBACK_MODEL]


class NinferClient(io.ComfyNode):
    """Points at a NInfer server, starting one if needed."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferClient",
            display_name="NInfer - Client",
            category="NInfer",
            description=(
                "Connection to a local NInfer server. Starts the server on first "
                "use and lets it shut down again once the queue has been idle."
            ),
            inputs=[
                io.String.Input(
                    id="base_url",
                    display_name="Base URL",
                    tooltip="NInfer's OpenAI-compatible endpoint",
                    default=config.BASE_URL,
                ),
                io.Boolean.Input(
                    id="auto_start",
                    display_name="Auto Start",
                    tooltip=(
                        "Start the server if it is not running. Turn this off to "
                        "use a server you launched yourself with infer.ps1."
                    ),
                    default=True,
                    label_on="start on demand",
                    label_off="server already running",
                ),
                io.Combo.Input(
                    id="model_file",
                    display_name="Model File",
                    tooltip="Artifact to load when this node starts the server",
                    options=config.list_models() or [config.DEFAULT_MODEL_FILE],
                    default=config.DEFAULT_MODEL_FILE,
                ),
                io.Int.Input(
                    id="idle_seconds",
                    display_name="Idle Shutdown (s)",
                    tooltip=(
                        "Stop the server after this long with no request. NInfer "
                        "cannot unload a model, so stopping the process is the "
                        "only way to give the VRAM back to ComfyUI."
                    ),
                    default=config.DEFAULT_IDLE_SECONDS,
                    min=config.MIN_IDLE_SECONDS,
                    max=config.MAX_IDLE_SECONDS,
                    step=10,
                ),
                io.Boolean.Input(
                    id="keep_alive",
                    display_name="Keep Alive",
                    tooltip="Never shut down automatically",
                    default=False,
                    label_on="stay loaded",
                    label_off="respect idle timeout",
                ),
                io.String.Input(
                    id="api_key",
                    display_name="API Key",
                    tooltip=(
                        "NInfer itself ignores this header entirely, so the default "
                        "placeholder is fine locally. It is here so the same nodes "
                        "can talk to any OpenAI-compatible endpoint that does check "
                        "credentials. Never leave it empty: an empty api_key makes "
                        "the openai client fail to connect."
                    ),
                    default=config.API_KEY,
                    placeholder="Leave '-' when the endpoint needs no key",
                ),
                io.Int.Input(
                    id="max_retries",
                    display_name="Max Retries",
                    tooltip="Retries on connection errors and 5xx responses",
                    default=1,
                    min=0,
                    max=10,
                ),
                io.Int.Input(
                    id="timeout",
                    display_name="Timeout (s)",
                    tooltip=(
                        "Whole-request budget. Generations here run for minutes, so "
                        "keep this generous."
                    ),
                    default=900,
                    min=1,
                    max=3600,
                ),
            ],
            outputs=[
                ParamClient.Output(
                    id="client",
                    display_name="Client",
                    tooltip="Pass to a NInfer chat node",
                ),
            ],
        )

    @classmethod
    def validate_inputs(cls, base_url: str | None) -> bool | str:
        if not base_url:
            return "base_url is required"
        if not base_url.startswith(("http://", "https://")):
            return "base_url must start with http:// or https://"
        return True

    @classmethod
    def execute(
        cls,
        base_url: str,
        auto_start: bool,
        model_file: str,
        idle_seconds: int,
        keep_alive: bool,
        api_key: str = config.API_KEY,
        max_retries: int = 1,
        timeout: int = 900,
    ) -> io.NodeOutput:
        from . import lifecycle

        if auto_start:
            idle = None if keep_alive else float(idle_seconds)
            if keep_alive:
                # Park the limit out of reach rather than skipping the manager.
                lifecycle.set_idle_override(None)
                lifecycle.ensure_running(model_file, idle_seconds=config.MAX_IDLE_SECONDS)
            else:
                lifecycle.ensure_running(model_file, idle_seconds=idle)
        else:
            lifecycle.touch()

        # The openai client rejects an empty key, so fall back to the placeholder
        # rather than letting a blank field look like a connection failure.
        resolved_key = (api_key or "").strip() or config.API_KEY

        return io.NodeOutput(
            OpenAI(
                api_key=resolved_key,
                base_url=base_url,
                max_retries=int(max_retries),
                timeout=float(timeout),
            )
        )

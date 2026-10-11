"""The generation node."""

from __future__ import annotations

import base64
import json
import time
from io import BytesIO
from typing import Any

import numpy as np
import torch
from comfy_api.latest import io, ui
from PIL import Image

from .i18n import DEFAULT_LANGUAGE, LANGUAGES, tr
from .iotypes import HistoryPayload, OptionsPayload, ParamClient, ParamHistory, ParamOptions

# Four reference images is the sweet spot observed on this machine: role-split
# conditioning stayed exactly correct through ten, and began confusing colours
# at twelve. Each 512px image costs about 256 prompt tokens.
IMAGE_SLOTS = 4


def comfy_image_to_data_url(image: torch.Tensor) -> str:
    """ComfyUI IMAGE tensor (B,H,W,C float 0..1) to a PNG data URL."""
    array = np.multiply(255.0, image.cpu().numpy())
    array = np.clip(array, 0, 255).astype(np.uint8)
    # Batches arrive as B frames; a single frame is the common case.
    if array.ndim == 4 and array.shape[0] == 1:
        array = array[0]
    pil = Image.fromarray(array)
    buffer = BytesIO()
    pil.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def _flatten_images(images: list[Any] | None) -> list[torch.Tensor]:
    """Collect the connected image slots in order, flattening batches."""
    frames: list[torch.Tensor] = []
    for entry in images or []:
        if entry is None:
            continue
        tensor = entry
        if isinstance(tensor, (list, tuple)):
            for item in tensor:
                if item is not None:
                    frames.extend(_flatten_images([item]))
            continue
        if tensor.ndim == 4:
            for i in range(tensor.shape[0]):
                frames.append(tensor[i : i + 1])
        elif tensor.ndim == 3:
            frames.append(tensor.unsqueeze(0))
        else:
            frames.append(tensor)
    return frames


def _usage_text(usage: Any, language: str = DEFAULT_LANGUAGE) -> str:
    if usage is None:
        return ""
    lines = [f"{tr('prompt_tokens', language)}: {usage.prompt_tokens}"]
    prompt_details = getattr(usage, "prompt_tokens_details", None)
    if prompt_details is not None:
        extras = []
        cached = getattr(prompt_details, "cached_tokens", None)
        if cached:
            extras.append(f"{tr('cached', language)}: {cached}")
        if extras:
            lines[0] += f" ({', '.join(extras)})"
    lines.append(f"{tr('completion_tokens', language)}: {usage.completion_tokens}")
    completion_details = getattr(usage, "completion_tokens_details", None)
    if completion_details is not None:
        extras = []
        reasoning = getattr(completion_details, "reasoning_tokens", None)
        if reasoning:
            extras.append(f"{tr('reasoning', language)}: {reasoning}")
        accepted = getattr(completion_details, "accepted_prediction_tokens", None)
        if accepted:
            extras.append(f"{tr('speculative_accepted', language)}: {accepted}")
        if extras:
            lines[1] += f" ({', '.join(extras)})"
    return "\n".join(lines)


class NinferChat(io.ComfyNode):
    """One chat completion against NInfer."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs: list[Any] = [
            ParamClient.Input(
                id="client",
                display_name="Client",
                tooltip="From a NInfer client node",
            ),
            io.String.Input(
                id="prompt",
                display_name="Prompt",
                tooltip="The user message",
                multiline=True,
                default="",
            ),
            io.String.Input(
                id="model",
                display_name="Model",
                tooltip="Leave empty to use the first model the server reports",
                default="",
            ),
            ParamOptions.Input(
                id="options",
                display_name="Options",
                optional=True,
                tooltip="Settings chain from the option nodes",
            ),
            ParamHistory.Input(
                id="history",
                display_name="History",
                optional=True,
                tooltip="Conversation so far",
            ),
            io.Boolean.Input(
                id="force_regen",
                display_name="Force Regen",
                tooltip="Always call the model, even when nothing changed",
                default=True,
                label_on="always regenerate",
                label_off="reuse cached result",
            ),
        ]
        # Cascading image sockets: slot 2 is meaningless until slot 1 is wired,
        # so each one is declared optional and documented as a chain.
        for slot in range(1, IMAGE_SLOTS + 1):
            inputs.append(
                io.Image.Input(
                    id=f"image_{slot}",
                    display_name=f"Image {slot}",
                    optional=True,
                    tooltip=(
                        "Reference image. Connect them in order; each slot adds "
                        "about 256 prompt tokens at 512px"
                    ),
                )
            )
        inputs.append(
            io.Combo.Input(
                id="language",
                display_name="Language",
                options=LANGUAGES,
                default=DEFAULT_LANGUAGE,
                tooltip=(
                    "Language for the preview and status text this node prints. "
                    "ComfyUI's own node labels follow the interface language."
                ),
            )
        )
        return io.Schema(
            node_id="NinferChat",
            display_name="NInfer - Chat",
            category="NInfer",
            description="Generates text, optionally conditioned on reference images.",
            inputs=inputs,
            outputs=[
                io.String.Output(
                    id="response",
                    display_name="Response",
                    tooltip="Visible reply text",
                ),
                io.String.Output(
                    id="reasoning",
                    display_name="Reasoning",
                    tooltip="Hidden thinking, when the model produced any",
                ),
                ParamHistory.Output(
                    id="history",
                    display_name="History",
                    tooltip="Conversation including this turn",
                ),
            ],
        )

    @classmethod
    def validate_inputs(cls, prompt: str) -> bool | str:
        if not prompt or not prompt.strip():
            return "prompt must not be empty"
        return True

    @classmethod
    def fingerprint_inputs(cls, **kwargs: Any) -> str:
        if kwargs.get("force_regen"):
            return str(time.time())
        kwargs.pop("force_regen", None)
        # Image tensors are not JSON serialisable; identity + shape is enough
        # to notice a change between runs.
        for key in list(kwargs):
            if key.startswith("image_"):
                value = kwargs[key]
                kwargs[key] = (
                    None
                    if value is None
                    else f"{id(value)}:{tuple(getattr(value, 'shape', ()))}"
                )
            elif key == "client":
                kwargs[key] = "client"
        return json.dumps(kwargs, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def execute(
        cls,
        client: Any,
        prompt: str,
        model: str = "",
        options: OptionsPayload | None = None,
        history: HistoryPayload | None = None,
        force_regen: bool = True,
        language: str = DEFAULT_LANGUAGE,
        **kwargs: Any,
    ) -> io.NodeOutput:
        from . import lifecycle
        from .client import discover_models

        settings = options.get_options_copy() if options is not None else {}
        system_prompt = settings.pop("system_prompt", None)
        settings.pop("__extra_body__", None)

        messages = history.get_messages_copy() if history is not None else []
        if system_prompt:
            if messages and messages[0].get("role") in ("system", "developer"):
                messages[0] = {"role": "system", "content": system_prompt}
            else:
                messages.insert(0, {"role": "system", "content": system_prompt})

        frames = _flatten_images([kwargs.get(f"image_{i}") for i in range(1, IMAGE_SLOTS + 1)])
        if frames:
            content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            for frame in frames:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": comfy_image_to_data_url(frame)},
                    }
                )
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": prompt})

        resolved_model = model.strip()
        if not resolved_model:
            available = discover_models()
            resolved_model = available[0] if available else "ninfer"
        elif "\n" in resolved_model or "进程号" in resolved_model or "healthy" in resolved_model.lower():
            # A multi-line server report was wired into the model input — most
            # likely the NInfer Server Control node's Status output. Surface that
            # instead of sending the blob to /v1/chat/completions and eating a 404.
            raise ValueError(tr("bad_model_input", language, value=resolved_model[:80]))

        lifecycle.enter()
        try:
            completion = client.chat.completions.create(
                model=resolved_model,
                messages=messages,
                n=1,
                **settings,
            )
        finally:
            lifecycle.leave()

        choice = completion.choices[0].message
        answer = choice.content or ""
        reasoning = getattr(choice, "reasoning_content", None) or ""

        messages.append({"role": "assistant", "content": answer})
        stats = _usage_text(getattr(completion, "usage", None), language)
        images_note = (
            f"\n{tr('images', language)}: {len(frames)}" if frames else ""
        )
        preview = f"{stats}{images_note}"

        return io.NodeOutput(
            answer,
            reasoning,
            HistoryPayload(messages),
            ui=ui.PreviewText(preview),
        )

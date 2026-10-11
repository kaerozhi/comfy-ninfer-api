"""Generation-settings nodes.

Each node carries one setting and merges it into an `OptionsPayload` coming
from the node before it, so settings read as a chain in the graph rather than
as one oversized widget panel.
"""

from __future__ import annotations

import json
from typing import Any

from comfy_api.latest import io

from .iotypes import OptionsPayload, ParamOptions

CATEGORY = "NInfer/Options"


class _OptionBase(io.ComfyNode):
    """Shared wiring: one setting in, merged options out."""

    key: str = ""

    @classmethod
    def _merge(cls, other_options: OptionsPayload | None, value: Any) -> OptionsPayload:
        options = other_options.get_options_copy() if other_options is not None else {}
        options[cls.key] = value
        return OptionsPayload(options)

    @classmethod
    def _chain_input(cls) -> Any:
        return ParamOptions.Input(
            id="other_options",
            display_name="Options",
            optional=True,
            tooltip="Options from the previous settings node",
        )

    @classmethod
    def _chain_output(cls) -> Any:
        return ParamOptions.Output(
            id="options",
            display_name="Options",
            tooltip="Merged settings",
        )


class NinferOptionSystemPrompt(_OptionBase):
    key = "system_prompt"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionSystemPrompt",
            display_name="NInfer - System Prompt",
            category=CATEGORY,
            description="Sets the system prompt and optionally injects a skill file.",
            inputs=[
                io.String.Input(
                    id="system_prompt",
                    display_name="System Prompt",
                    tooltip="Instructions applied to the whole conversation",
                    multiline=True,
                    default="",
                ),
                io.Combo.Input(
                    id="skill",
                    display_name="Skill File",
                    tooltip=(
                        "Markdown appended to the system prompt. Files come from "
                        f"{config_skills_dir()}."
                    ),
                    options=config_skill_options(),
                    default=config_no_skill(),
                ),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(
        cls,
        system_prompt: str,
        skill: str,
        other_options: OptionsPayload | None = None,
    ) -> io.NodeOutput:
        from .config import read_skill

        parts: list[str] = []
        if system_prompt and system_prompt.strip():
            parts.append(system_prompt.strip())
        skill_text = read_skill(skill)
        if skill_text:
            parts.append(skill_text.strip())
        return io.NodeOutput(cls._merge(other_options, "\n\n".join(parts)))


class NinferOptionTemperature(_OptionBase):
    key = "temperature"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionTemperature",
            display_name="NInfer - Temperature",
            category=CATEGORY,
            inputs=[
                io.Float.Input(id="temperature", default=0.7, min=0.0, max=2.0, step=0.05),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(cls, temperature: float, other_options: OptionsPayload | None = None) -> io.NodeOutput:
        return io.NodeOutput(cls._merge(other_options, temperature))


class NinferOptionMaxTokens(_OptionBase):
    key = "max_tokens"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionMaxTokens",
            display_name="NInfer - Max Tokens",
            category=CATEGORY,
            description=(
                "Upper bound on generated tokens. The model thinks before it "
                "answers, so a small budget can be spent entirely on reasoning "
                "and leave the visible reply empty."
            ),
            inputs=[
                io.Int.Input(id="max_tokens", default=2048, min=1, max=32768, step=64),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(cls, max_tokens: int, other_options: OptionsPayload | None = None) -> io.NodeOutput:
        return io.NodeOutput(cls._merge(other_options, int(max_tokens)))


class NinferOptionReasoningEffort(_OptionBase):
    key = "reasoning_effort"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionReasoningEffort",
            display_name="NInfer - Reasoning Effort",
            category=CATEGORY,
            description=(
                "How long the model thinks before answering. `low` keeps most of "
                "the token budget for the visible reply."
            ),
            inputs=[
                io.Combo.Input(
                    id="reasoning_effort",
                    options=["low", "medium", "xhigh"],
                    default="low",
                    tooltip="xhigh spends a lot of tokens on hidden reasoning",
                ),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(
        cls,
        reasoning_effort: str,
        other_options: OptionsPayload | None = None,
    ) -> io.NodeOutput:
        return io.NodeOutput(cls._merge(other_options, reasoning_effort))


class NinferOptionTopP(_OptionBase):
    key = "top_p"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionTopP",
            display_name="NInfer - Top P",
            category=CATEGORY,
            inputs=[
                io.Float.Input(id="top_p", default=0.95, min=0.0, max=1.0, step=0.01),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(cls, top_p: float, other_options: OptionsPayload | None = None) -> io.NodeOutput:
        return io.NodeOutput(cls._merge(other_options, top_p))


class NinferOptionTopK(_OptionBase):
    key = "top_k"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionTopK",
            display_name="NInfer - Top K",
            category=CATEGORY,
            inputs=[
                io.Int.Input(id="top_k", default=20, min=0, max=1000),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(cls, top_k: int, other_options: OptionsPayload | None = None) -> io.NodeOutput:
        return io.NodeOutput(cls._merge(other_options, int(top_k)))


class NinferOptionSeed(_OptionBase):
    key = "seed"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionSeed",
            display_name="NInfer - Seed",
            category=CATEGORY,
            inputs=[
                io.Int.Input(
                    id="seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFF,
                    control_after_generate=True,
                    display_mode=io.NumberDisplay.number,
                ),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def execute(cls, seed: int, other_options: OptionsPayload | None = None) -> io.NodeOutput:
        return io.NodeOutput(cls._merge(other_options, int(seed)))


class NinferOptionExtraBody(_OptionBase):
    key = "__extra_body__"

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferOptionExtraBody",
            display_name="NInfer - Extra Body",
            category=CATEGORY,
            description="Raw JSON merged into the request body, for anything not covered above.",
            inputs=[
                io.String.Input(
                    id="extra_body",
                    display_name="Extra Body (JSON)",
                    multiline=True,
                    default="{}",
                ),
                cls._chain_input(),
            ],
            outputs=[cls._chain_output()],
        )

    @classmethod
    def validate_inputs(cls, extra_body: str) -> bool | str:
        try:
            parsed = json.loads(extra_body or "{}")
        except json.JSONDecodeError as exc:
            return f"extra_body is not valid JSON: {exc}"
        if not isinstance(parsed, dict):
            return "extra_body must be a JSON object"
        return True

    @classmethod
    def execute(cls, extra_body: str, other_options: OptionsPayload | None = None) -> io.NodeOutput:
        options = other_options.get_options_copy() if other_options is not None else {}
        try:
            options.update(json.loads(extra_body or "{}"))
        except json.JSONDecodeError:
            pass
        return io.NodeOutput(OptionsPayload(options))


def config_skills_dir() -> str:
    from .config import SKILLS_DIR

    return str(SKILLS_DIR)


def config_skill_options() -> list[str]:
    from .config import NO_SKILL, list_skills

    return [NO_SKILL] + list_skills()


def config_no_skill() -> str:
    from .config import NO_SKILL

    return NO_SKILL

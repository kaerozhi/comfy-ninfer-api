"""Explicit control over the NInfer server process."""

from __future__ import annotations

from comfy_api.latest import io, ui

from . import lifecycle
from .i18n import DEFAULT_LANGUAGE, LANGUAGES, tr


class NinferServer(io.ComfyNode):
    """Start, stop, or wait on the server from inside a graph."""

    @classmethod
    def define_schema(cls) -> io.Schema:
        return io.Schema(
            node_id="NinferServer",
            display_name="NInfer - Server Control",
            category="NInfer",
            description=(
                "Drives the NInfer process directly. Useful when a workflow should "
                "hold the GPU itself and hand it back when finished."
            ),
            inputs=[
                io.Combo.Input(
                    id="action",
                    display_name="Action",
                    options=["ensure running", "stop", "keep alive", "status"],
                    default="ensure running",
                ),
                io.Combo.Input(
                    id="model_file",
                    display_name="Model File",
                    options=list(lifecycle.config.list_models()) or [lifecycle.config.DEFAULT_MODEL_FILE],
                    default=lifecycle.config.DEFAULT_MODEL_FILE,
                ),
                io.Boolean.Input(
                    id="force",
                    display_name="Force Kill",
                    tooltip="Skip the graceful shutdown and kill the process outright",
                    default=False,
                    label_on="kill now",
                    label_off="graceful",
                ),
                io.Combo.Input(
                    id="language",
                    display_name="Language",
                    options=LANGUAGES,
                    default=DEFAULT_LANGUAGE,
                    tooltip=(
                        "Language for the status text this node prints. "
                        "ComfyUI's own node labels follow the interface language."
                    ),
                ),
            ],
            outputs=[
                io.String.Output(id="status", display_name="Status", tooltip="Result of the action"),
                io.Boolean.Output(id="healthy", display_name="Healthy", tooltip="Server is answering"),
            ],
        )

    @classmethod
    def execute(
        cls,
        action: str,
        model_file: str,
        force: bool = False,
        language: str = DEFAULT_LANGUAGE,
    ) -> io.NodeOutput:
        if action == "stop":
            stopped = lifecycle.stop(force=force)
            text = tr("stopped" if stopped else "already_stopped", language)
        elif action == "keep alive":
            lifecycle.set_idle_override(None)
            lifecycle.ensure_running(model_file, idle_seconds=lifecycle.config.MAX_IDLE_SECONDS)
            text = tr("keep_alive", language)
        elif action == "status":
            text = tr("status", language)
        else:
            lifecycle.ensure_running(model_file)
            text = tr("running", language)

        snapshot = lifecycle.status()
        healthy = tr("yes" if snapshot["healthy"] else "no", language)
        busy = tr("yes" if snapshot["comfy_busy"] else "no", language)
        report = (
            f"{text}\n"
            f"{tr('healthy', language)}: {healthy}\n"
            f"{tr('pid', language)}: {snapshot['managed_pid'] or snapshot['listening_pid'] or tr('none', language)}\n"
            f"{tr('in_flight', language)}: {snapshot['in_flight']}\n"
            f"{tr('idle', language)}: {snapshot['idle_seconds']}s / {snapshot['idle_limit']}s\n"
            f"{tr('comfy_busy', language)}: {busy}"
        )
        return io.NodeOutput(report, snapshot["healthy"], ui=ui.PreviewText(report))

"""Runtime strings for the two supported languages.

ComfyUI's locale files only reach the node definition, so anything the pack
prints at execution time — the usage report, the server status — is translated
here instead.
"""

from __future__ import annotations

# Language choices offered on the nodes. The frontend locale is not visible to
# the backend, so nodes that print runtime text expose this explicitly.
LANGUAGES: list[str] = ["zh", "en"]
LANGUAGE_LABELS: dict[str, str] = {"en": "English", "zh": "中文"}
DEFAULT_LANGUAGE = "zh"

# Each entry: key -> (english, chinese). `{name}` placeholders are filled by
# `tr`; keep them identical in both languages.
_STRINGS: dict[str, tuple[str, str]] = {
    "lang_name": ("English", "中文"),
    "prompt_tokens": ("Prompt tokens", "提示词 tokens"),
    "completion_tokens": ("Completion tokens", "生成 tokens"),
    "cached": ("cached", "命中缓存"),
    "reasoning": ("reasoning", "思考"),
    "speculative_accepted": ("speculative accepted", "投机接受"),
    "images": ("images", "图像"),
    "stopped": ("stopped", "已停止"),
    "already_stopped": ("already stopped", "本就未运行"),
    "keep_alive": ("keep alive", "保持常驻"),
    "status": ("status", "状态"),
    "running": ("running", "运行中"),
    "healthy": ("healthy", "健康"),
    "pid": ("pid", "进程号"),
    "in_flight": ("in flight", "进行中"),
    "idle": ("idle", "空闲"),
    "comfy_busy": ("comfy busy", "ComfyUI 忙碌"),
    "yes": ("yes", "是"),
    "no": ("no", "否"),
    "none": ("-", "-"),
    "unknown_action": ("unknown action: {name}", "未知操作：{name}"),
    "server_unavailable": (
        "server did not become healthy in time",
        "服务未能在超时内就绪",
    ),
}


def normalise(language: str | None) -> str:
    """Map a ComfyUI locale code onto a supported language."""
    if not language:
        return "en"
    code = str(language).strip().lower().replace("_", "-")
    if code.startswith("zh"):
        return "zh"
    return "en"


def tr(key: str, language: str | None = "en", **kwargs: object) -> str:
    """Look up a runtime string, falling back to English then to the key."""
    entry = _STRINGS.get(key)
    if entry is None:
        return key
    text = entry[1] if normalise(language) == "zh" else entry[0]
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text

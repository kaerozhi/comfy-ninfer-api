"""Filesystem layout and defaults for the NInfer ComfyUI nodes.

Everything is derived from the ComfyUI server's own folder paths, so the pack
keeps working after a directory move or on somebody else's machine.
"""

from __future__ import annotations

import os
from pathlib import Path

# --- ComfyUI folder roots -------------------------------------------------
# folder_paths is importable because custom nodes are loaded with the ComfyUI
# root already on sys.path.
try:
    import folder_paths

    INPUT_DIR = Path(folder_paths.get_input_directory()).resolve()
    BASE_DIR = Path(folder_paths.base_path).resolve()
except Exception:  # pragma: no cover - only hit outside a real ComfyUI
    INPUT_DIR = Path(os.environ.get("COMFY_INPUT_DIR", "input")).resolve()
    BASE_DIR = Path.cwd().resolve()

# Skill markdown lives outside this pack so a workflow can reuse the same files
# across machines and the pack needs no rebuild when one is added.
#
# NOTE: `--input-directory` does NOT move this. `folder_paths.get_input_directory()`
# always reports the built-in `<ComfyUI>/input`, even when the server loads images
# from somewhere else, so deriving from it alone silently reads an empty tree.
#
# Resolution order, first hit wins:
#   1. NINFER_SKILLS_DIR — explicit override, always the right answer when set
#   2. <ComfyUI>/input/skills — the portable default
#   3. <ComfyUI>/../Input/skills — sibling layout used when --input-directory
#      points outside the ComfyUI tree (this deployment)
# Candidates are only accepted if they exist, so an absent one falls through
# instead of silently listing nothing.
SKILLS_DIR_CANDIDATES = [
    Path(p)
    for p in (
        os.environ.get("NINFER_SKILLS_DIR"),
        INPUT_DIR / "skills",
        BASE_DIR.parent / "Input" / "skills",
    )
    if p
]


def _pick_skills_dir() -> Path:
    for candidate in SKILLS_DIR_CANDIDATES:
        try:
            if candidate.is_dir():
                return candidate
        except OSError:
            continue
    # Nothing exists yet; report the portable default so the tooltip points
    # somewhere sensible and creating it there starts working immediately.
    return INPUT_DIR / "skills"


SKILLS_DIR = _pick_skills_dir()

# --- NInfer deployment ----------------------------------------------------
# All of these are guesses that a real installation overrides; nothing here is
# assumed to exist. The intended layout is:
#   <NINFER_ROOT>/models/*.ninfer                        (artifacts)
#   <NINFER_GSQ_ROOT>/build-win/apps/ninfer-serve.exe    (engine binary)
# so NINFER_SERVE_EXE and NINFER_MODELS_DIR are the two that usually matter.
NINFER_ROOT = Path(os.environ.get("NINFER_ROOT", r"D:\AI\Ninfer"))
NINFER_GSQ_ROOT = Path(os.environ.get("NINFER_GSQ_ROOT", r"D:\AI\Ninfer-gsq"))

SERVE_EXE = Path(
    os.environ.get(
        "NINFER_SERVE_EXE",
        NINFER_GSQ_ROOT / "build-win" / "apps" / "ninfer-serve.exe",
    )
)
MODELS_DIR = Path(os.environ.get("NINFER_MODELS_DIR", NINFER_ROOT / "models"))

# Artifact used when the model input is left empty. Only a fallback: the model
# input lists whatever is actually in MODELS_DIR, and any name works.
DEFAULT_MODEL_FILE = os.environ.get(
    "NINFER_MODEL_FILE",
    "Huihui-Qwen3.8-27B-abliterated-Swift-1.5-GSQ-RCO-IQ3_S-mtp.ninfer",
)

# --- Server -----------------------------------------------------------------
HOST = os.environ.get("NINFER_HOST", "127.0.0.1")
PORT = int(os.environ.get("NINFER_PORT", "8080"))
BASE_URL = f"http://{HOST}:{PORT}/v1"

# NInfer has no auth, but the OpenAI-compatible layer still demands a key.
API_KEY = "ninfer-local"

HEALTH_URL = f"http://{HOST}:{PORT}/health"

# --- Shutdown policy --------------------------------------------------------
# NInfer cannot eject a model: the only way to give VRAM back is to kill the
# process. A cold start costs ~5.6s, so the server is kept warm while it is
# being used and torn down once the callers have gone quiet.
DEFAULT_IDLE_SECONDS = 120
MIN_IDLE_SECONDS = 30
MAX_IDLE_SECONDS = 3600

# `/health` polls must not be confused with real work; the manager counts
# in-flight `execute()` calls separately.
POLL_INTERVAL_SECONDS = 1.0
STARTUP_TIMEOUT_SECONDS = 180.0
SHUTDOWN_TIMEOUT_SECONDS = 30.0

# --- Skill files -------------------------------------------------------------
SKILL_SUFFIXES = (".md", ".txt")
NO_SKILL = "(none)"

# Skills may be grouped in sub-directories, one per model or task. The dropdown
# shows a POSIX-style path relative to the skills root (`qwen-image-2.1/film.md`)
# so a flat file and a nested one never collide on name. `SKILL_MAX_DEPTH` counts
# path components below the root, so 3 allows `a/b/c.md` but not `a/b/c/d.md`;
# past that the combo gets unwieldy and usually means the grouping has drifted.
SKILL_MAX_DEPTH = 3


def skills_available() -> bool:
    return SKILLS_DIR.is_dir()


def _skill_depth(relative: str) -> int:
    """Path components below the skills root: `a.md` -> 1, `a/b.md` -> 2."""
    return len([part for part in relative.replace("\\", "/").split("/") if part])


def list_skills() -> list[str]:
    """Skill paths relative to SKILLS_DIR. Never raises.

    Top-level files come back as bare names, nested ones as `dir/name`, so both
    layouts keep working and older graphs keep resolving.
    """
    if not skills_available():
        return []
    found: list[str] = []
    try:
        for root, dirs, files in os.walk(SKILLS_DIR):
            # Skip hidden and cache directories so `.git` never leaks in. A
            # sub-directory here would push its files one level too deep, so
            # prune it now rather than filtering each file afterwards.
            depth = len(Path(root).relative_to(SKILLS_DIR).parts)
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and depth + 2 <= SKILL_MAX_DEPTH
            ]
            for name in files:
                if not name.lower().endswith(SKILL_SUFFIXES):
                    continue
                try:
                    relative = (Path(root) / name).relative_to(SKILLS_DIR)
                except ValueError:
                    continue
                posix = relative.as_posix()
                if _skill_depth(posix) > SKILL_MAX_DEPTH:
                    continue
                found.append(posix)
    except OSError:
        return []

    # Directory order first, so a group reads as one block in the dropdown.
    found.sort(key=lambda rel: (os.path.dirname(rel).lower(), rel.lower()))
    return found


def read_skill(name: str | None) -> str:
    """Read one skill file. Returns '' for the sentinel or a missing file.

    Accepts both `name.md` and `group/name.md`; any path that escapes the
    skills root resolves outside it and is refused, and anything deeper than
    the dropdown offers is refused too so the two stay consistent.
    """
    if not name or name == NO_SKILL:
        return ""
    # Normalise Windows-style separators so a hand-typed value still works.
    relative = str(name).replace("\\", "/").strip()
    if not relative or _skill_depth(relative) > SKILL_MAX_DEPTH:
        return ""
    candidate = SKILLS_DIR / relative
    # Refuse to escape the skills directory via ../ or an absolute path.
    try:
        candidate.resolve().relative_to(SKILLS_DIR.resolve())
    except (ValueError, OSError):
        return ""
    if not candidate.is_file():
        return ""
    try:
        return candidate.read_text(encoding="utf-8")
    except OSError:
        return ""


def list_models() -> list[str]:
    """Artifact file names found on disk. Never raises."""
    if not MODELS_DIR.is_dir():
        return []
    try:
        return sorted(p.name for p in MODELS_DIR.glob("*.ninfer"))
    except OSError:
        return []

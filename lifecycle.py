"""Process lifecycle for the NInfer server.

NInfer cannot eject a loaded model: the weights live in a single-process
device arena that is built once at startup and never torn down. Measured on
this machine, the only two facts that matter are:

  * a cold start costs about 5-6 seconds, and
  * while it runs it holds ~17.6 GiB of VRAM, which starves ComfyUI.

So the server is treated as an expensive, shared, lazily-started resource:
started on first use, kept alive while callers are active, and stopped once
they have been quiet for `idle_seconds`.

The idle decision needs all three of:

  1. no `execute()` call is in flight,
  2. no ComfyUI prompt is queued or running,
  3. `idle_seconds` have passed since the last activity.

Condition 2 matters because ComfyUI edges are evaluated lazily: a graph may
call a NInfer node and then spend a minute on a sampler with no NInfer call
pending. Without it the server would be torn down mid-workflow and the next
NInfer node in the same graph would pay a cold start.
"""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from . import config

LOG = logging.getLogger("ninfer-api")

# --- Process handle ---------------------------------------------------------
_lock = threading.RLock()
_process: subprocess.Popen | None = None
_log_handle = None
_started_at: float = 0.0

# --- Activity tracking ------------------------------------------------------
_in_flight = 0
_last_activity = 0.0
_idle_seconds = config.DEFAULT_IDLE_SECONDS
_idle_override: float | None = None
_cleanup_running = False


# ---------------------------------------------------------------------------
# Server reachability
# ---------------------------------------------------------------------------
def server_healthy(timeout: float = 2.0) -> bool:
    """True when something answers NInfer's /health with status ok."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(config.HEALTH_URL, timeout=timeout) as resp:
            if resp.status != 200:
                return False
            body = resp.read().decode("utf-8", "replace")
        return '"ok"' in body
    except Exception:
        return False


def _listening_pid() -> int | None:
    """PID holding the NInfer port, or None. Uses netstat so it needs no admin."""
    try:
        completed = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    blob = completed.stdout or b""
    if isinstance(blob, bytes):
        blob = blob.decode("utf-8", errors="replace")
    needle = f":{config.PORT} "
    for line in blob.splitlines():
        if needle not in line or "LISTENING" not in line:
            continue
        parts = line.split()
        if parts and parts[-1].isdigit():
            return int(parts[-1])
    return None


# ---------------------------------------------------------------------------
# Start / stop
# ---------------------------------------------------------------------------
def _resolve_model_path(model_file: str | None) -> Path:
    name = model_file or config.DEFAULT_MODEL_FILE
    path = Path(name)
    if not path.is_absolute():
        path = config.MODELS_DIR / name
    return path


def _launch(model_file: str | None, idle_seconds: float) -> None:
    """Start the server process. Caller must hold the lock."""
    global _process, _log_handle, _started_at

    if not config.SERVE_EXE.is_file():
        raise RuntimeError(f"ninfer-serve.exe not found at {config.SERVE_EXE}")

    model_path = _resolve_model_path(model_file)
    if not model_path.is_file():
        raise RuntimeError(
            f"model not found: {model_path}\n"
            f"Available in {config.MODELS_DIR}: {', '.join(config.list_models()) or '(none)'}"
        )

    log_path = Path(config.NINFER_ROOT) / "comfy-ninfer-server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _log_handle = open(log_path, "ab", buffering=0)
    _log_handle.write(
        f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} starting {model_path.name} =====\n".encode()
    )

    args = [
        str(config.SERVE_EXE),
        str(model_path),
        "--host",
        config.HOST,
        "--port",
        str(config.PORT),
    ]
    # Model geometry is read from the artifact; the rest is the coexistence
    # profile tuned for running beside ComfyUI on a 24 GiB card.
    args += [
        "--max-context",
        "16384",
        "--kv-capacity",
        "16384",
        "--max-concurrency",
        "1",
        "--kv-dtype",
        "rk4v4-e8",
        "--spec",
        "mtp",
        "--draft-tokens",
        "3",
        "--lm-head-draft",
        # Vision: the tower is only 0.38 GiB of the artifact and overlay
        # residency costs ~0.36 GiB of VRAM, so images are always available.
        "--vision",
        "--vision-residency",
        "overlay",
    ]

    LOG.info("starting NInfer: %s", model_path.name)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    _process = subprocess.Popen(
        args,
        stdout=_log_handle,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        cwd=str(Path(config.SERVE_EXE).parent),
        creationflags=creationflags,
    )
    _started_at = time.time()


def _wait_healthy(timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if server_healthy(timeout=2.0):
            return True
        with _lock:
            if _process is not None and _process.poll() is not None:
                return False
        time.sleep(0.5)
    return False


def ensure_running(model_file: str | None = None, idle_seconds: float | None = None) -> bool:
    """Make sure a server is answering. Returns True if it is usable.

    Adopts an already-listening server instead of spawning a second one, so
    the node pack composes with a server started from `infer.ps1`.
    """
    global _idle_seconds, _idle_override, _last_activity

    if idle_seconds is not None:
        _idle_seconds = max(config.MIN_IDLE_SECONDS, min(config.MAX_IDLE_SECONDS, float(idle_seconds)))

    with _lock:
        touch()
        if server_healthy():
            return True
        if _process is not None and _process.poll() is None:
            # We own a process that has not opened its port yet.
            pass
        else:
            _launch(model_file, _idle_seconds)

    ok = _wait_healthy(config.STARTUP_TIMEOUT_SECONDS)
    if not ok:
        LOG.error("NInfer did not become healthy within %.0fs", config.STARTUP_TIMEOUT_SECONDS)
        stop(force=True)
        return False
    LOG.info("NInfer ready after %.1fs", time.time() - _started_at)
    return True


def stop(force: bool = False) -> bool:
    """Shut the server down and release its VRAM.

    A graceful stop is a CTRL_C_EVENT delivered into the target console; that
    is what trips NInfer's SIGINT handler. Killing the PID directly works too
    but skips its clean shutdown path.
    """
    global _process, _log_handle

    with _lock:
        proc = _process
        _process = None

    target_pid = proc.pid if proc is not None and proc.poll() is None else None
    if target_pid is None:
        target_pid = _listening_pid() if server_healthy() else None

    if target_pid is None:
        _close_log()
        return False

    if not force and not _send_ctrl_c(target_pid):
        force = True

    if force:
        _kill_tree(target_pid)
    else:
        deadline = time.time() + config.SHUTDOWN_TIMEOUT_SECONDS
        while time.time() < deadline:
            if not _pid_alive(target_pid):
                break
            time.sleep(0.25)
        else:
            LOG.warning("graceful stop timed out; forcing pid %d", target_pid)
            _kill_tree(target_pid)

    _close_log()
    LOG.info("NInfer stopped (pid %d)", target_pid)
    return True


def _close_log() -> None:
    global _log_handle
    if _log_handle is not None:
        try:
            _log_handle.close()
        except OSError:
            pass
        _log_handle = None


def _pid_alive(pid: int) -> bool:
    # A cheap os.kill probe avoids spawning a console tool on every poll; on
    # Windows it raises OSError for a dead pid rather than signalling anything.
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        pass
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return False
    stdout = completed.stdout or b""
    if isinstance(stdout, bytes):
        stdout = stdout.decode("utf-8", errors="replace")
    return str(pid) in stdout


def _run_quiet(args: list[str], timeout: float = 20) -> None:
    """Run a console tool, decoding its output defensively.

    Windows tools emit OEM-codepage bytes that are not valid UTF-8, so a
    text-mode capture can raise out of a background thread.
    """
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception as exc:  # pragma: no cover
        LOG.warning("%s failed: %s", args[0], exc)
        return
    blob = (completed.stdout or b"") + (completed.stderr or b"")
    if blob:
        LOG.debug("%s: %s", args[0], blob.decode("utf-8", errors="replace").strip())


def _kill_tree(pid: int) -> None:
    _run_quiet(["taskkill", "/PID", str(pid), "/T", "/F"])


def _send_ctrl_c(target_pid: int) -> bool:
    """Attach to the target's console and post CTRL_C_EVENT. Best effort."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.FreeConsole()
        if not kernel32.AttachConsole(wintypes.DWORD(target_pid)):
            return False
        kernel32.SetConsoleCtrlHandler(None, True)
        posted = bool(kernel32.GenerateConsoleCtrlEvent(0, 0))
        kernel32.FreeConsole()
        return posted
    except Exception as exc:  # pragma: no cover
        LOG.debug("ctrl-c delivery failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Idle accounting
# ---------------------------------------------------------------------------
def touch() -> None:
    global _last_activity
    _last_activity = time.time()


def enter() -> None:
    """Mark one generation as started."""
    global _in_flight
    with _lock:
        _in_flight += 1
        touch()


def leave() -> None:
    """Mark one generation as finished."""
    global _in_flight
    with _lock:
        _in_flight = max(0, _in_flight - 1)
        touch()


def _comfy_busy() -> bool:
    """True while ComfyUI has queued or running work.

    Imported lazily: this module is also imported by node schema validation,
    which runs before `execution` is fully initialised.
    """
    try:
        from execution import PromptQueue  # type: ignore
    except Exception:
        return False
    try:
        import server  # type: ignore

        prompt_server = getattr(server, "PromptServer", None)
        instance = getattr(prompt_server, "instance", None)
        if instance is None:
            return False
        queue = getattr(instance, "prompt_queue", None)
        if queue is None:
            return False
        if getattr(queue, "currently_running", None):
            return True
        pending = getattr(queue, "queue", None)
        if pending is not None:
            try:
                if len(pending) > 0:
                    return True
            except TypeError:
                pass
        return False
    except Exception:
        return False


def should_stop() -> bool:
    with _lock:
        if _in_flight > 0:
            return False
        if not server_healthy(timeout=1.0):
            return False
        idle = _idle_override if _idle_override is not None else _idle_seconds
        if time.time() - _last_activity < idle:
            return False
    return not _comfy_busy()


def set_idle_override(seconds: float | None) -> None:
    """Force a stop after `seconds`, or None to use the per-call value."""
    global _idle_override
    with _lock:
        _idle_override = seconds
        touch()


# ---------------------------------------------------------------------------
# Background reaper
# ---------------------------------------------------------------------------
def _reaper() -> None:
    while True:
        time.sleep(config.POLL_INTERVAL_SECONDS)
        try:
            if should_stop():
                LOG.info("idle threshold reached; stopping NInfer to free VRAM")
                stop()
        except Exception as exc:  # pragma: no cover
            LOG.debug("reaper error: %s", exc)


_reaper_thread: threading.Thread | None = None


def start_reaper() -> None:
    global _reaper_thread
    if _reaper_thread is not None and _reaper_thread.is_alive():
        return
    _reaper_thread = threading.Thread(target=_reaper, name="ninfer-idle-reaper", daemon=True)
    _reaper_thread.start()
    atexit.register(lambda: stop(force=True))


def status() -> dict:
    """Snapshot for the control node's UI and for diagnostics."""
    with _lock:
        proc = _process
        return {
            "healthy": server_healthy(timeout=1.0),
            "managed_pid": proc.pid if proc is not None and proc.poll() is None else None,
            "listening_pid": _listening_pid(),
            "in_flight": _in_flight,
            "idle_seconds": round(time.time() - _last_activity, 1) if _last_activity else None,
            "idle_limit": _idle_override if _idle_override is not None else _idle_seconds,
            "comfy_busy": _comfy_busy(),
            "model_file": config.DEFAULT_MODEL_FILE,
        }

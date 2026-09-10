"""
Offline scene execution for the agent.

Runs a scene as a HEADLESS subprocess of the Python agent
(not via the editor), capturing its stdout/stderr so the
agent can autonomously check its own work for errors -
the behavioral feedback half of the edit -> run -> fix
loop. Godot's editor debugger consumes a game's built-in
output/error messages before editor plugins can see them
(verified empirically on 4.7.2), so editor-side output
capture is not viable; owning the subprocess is.

This is the project's second Python-side tool: the scene
runs on this machine via the configured engine binary,
never through the Godot bridge. Output is bounded and
never fabricated; a scene that outlives the timeout is
reported as timed out, never as successful.
"""

import os
import subprocess
import time

from config.settings import GODOT_BINARY_PATH, PROJECT_PATH


DEFAULT_TIMEOUT_SECONDS = 30

MAX_TIMEOUT_SECONDS = 120

MAX_OUTPUT_CHARS = 8000


def _bound_output(text):
    """Keep the tail of long output, report truncation."""

    if text is None:
        return "", False

    if len(text) <= MAX_OUTPUT_CHARS:
        return text, False

    return (
        "...[truncated]...\n" + text[-MAX_OUTPUT_CHARS:],
        True,
    )


def run_scene_offline(
    scene_path,
    timeout=None,
):
    """
    Run one scene headless via the configured engine
    binary and return its output.

    The scene runs as a real Godot process against the
    project (equivalent to running it from the command
    line), with a bounded timeout: a scene that never
    exits is killed and reported as timed out. Exit code,
    stdout, and stderr are returned verbatim (bounded)
    so script errors and print output are visible to the
    agent without any editor or instrumentation.
    """

    if not isinstance(scene_path, str) or not scene_path.strip():
        return {
            "success": False,
            "error": (
                "run_scene_offline requires a non-empty "
                "scene_path."
            ),
        }

    scene_path = scene_path.strip()

    if not scene_path.endswith(".tscn"):
        return {
            "success": False,
            "error": (
                "run_scene_offline requires a scene_path "
                "ending in .tscn."
            ),
        }

    effective_timeout = DEFAULT_TIMEOUT_SECONDS

    if timeout is not None:
        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or timeout < 1
            or timeout > MAX_TIMEOUT_SECONDS
        ):
            return {
                "success": False,
                "error": (
                    "run_scene_offline timeout must be an "
                    "integer between 1 and "
                    + str(MAX_TIMEOUT_SECONDS)
                    + "."
                ),
            }

        effective_timeout = timeout

    if not GODOT_BINARY_PATH:
        return {
            "success": False,
            "error": (
                "run_scene_offline requires GODOT_BINARY_PATH "
                "to be configured (see config/settings.py)."
            ),
        }

    if not os.path.isfile(GODOT_BINARY_PATH):
        return {
            "success": False,
            "error": (
                "run_scene_offline: the configured engine "
                "binary was not found: "
                + GODOT_BINARY_PATH
                + ". Set GODOT_BINARY_PATH (see "
                + "config/settings.py)."
            ),
        }

    command = [
        GODOT_BINARY_PATH,
        "--headless",
        "--path",
        PROJECT_PATH,
        scene_path,
    ]

    started = time.monotonic()

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=effective_timeout,
        )

        timed_out = False
        exit_code = completed.returncode
        stdout = completed.stdout or ""
        stderr = completed.stderr or ""

    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = None
        stdout = (
            error.stdout.decode("utf-8", errors="replace")
            if isinstance(error.stdout, bytes)
            else (error.stdout or "")
        )
        stderr = (
            error.stderr.decode("utf-8", errors="replace")
            if isinstance(error.stderr, bytes)
            else (error.stderr or "")
        )

    duration_s = time.monotonic() - started

    bounded_stdout, stdout_truncated = _bound_output(stdout)
    bounded_stderr, stderr_truncated = _bound_output(stderr)

    return {
        "success": True,
        "action": "run_scene_offline",
        "scene_path": scene_path,
        "timeout_seconds": effective_timeout,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "duration_s": round(duration_s, 2),
        "stdout": bounded_stdout,
        "stdout_truncated": stdout_truncated,
        "stderr": bounded_stderr,
        "stderr_truncated": stderr_truncated,
        "script_errors_detected": "SCRIPT ERROR" in stderr,
    }

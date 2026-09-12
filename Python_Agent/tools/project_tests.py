"""
Project test runner for the agent: executes every headless
test harness in addons/Execution_Agent/tests via the
configured engine binary and reports a structured pass/fail
summary - the self-check tool that lets the agent validate
its own work in one step.

Like run_scene_offline, this owns subprocesses on this
machine and never touches the editor bridge. A harness is
PASS only when its process exits 0 AND its log contains no
"Assertion failed" line; anything else is reported honestly
with the harness name so the agent can drill in.
"""

import os
import re
import subprocess
import time

from config.settings import GODOT_BINARY_PATH, PROJECT_PATH


HARNESS_GLOB = "addons/Execution_Agent/tests/*_harness.gd"

# Harnesses that are known to never terminate headless
# (pre-existing quirks) or that require a live editor.

SKIPPED_HARNESSES = (
    "get_undo_history_summary_harness.gd",
)

DEFAULT_HARNESS_TIMEOUT = 120

MAX_TIMEOUT = 600

MAX_LOG_CHARS = 2000


def _list_harnesses():
    tests_dir = os.path.join(
        PROJECT_PATH, "addons", "Execution_Agent", "tests"
    )

    if not os.path.isdir(tests_dir):
        return []

    harnesses = []

    for name in sorted(os.listdir(tests_dir)):

        if not name.endswith("_harness.gd"):
            continue

        if name in SKIPPED_HARNESSES:
            continue

        harnesses.append(name)

    return harnesses


def run_project_tests(
    timeout=None,
):
    """
    Run every headless harness and return a structured
    summary. timeout bounds EACH harness (10-600 s,
    default 120).
    """

    effective_timeout = DEFAULT_HARNESS_TIMEOUT

    if timeout is not None:

        if (
            not isinstance(timeout, int)
            or isinstance(timeout, bool)
            or timeout < 10
            or timeout > MAX_TIMEOUT
        ):
            return {
                "success": False,
                "error": (
                    "run_project_tests timeout must be an "
                    "integer between 10 and "
                    + str(MAX_TIMEOUT)
                    + "."
                ),
            }

        effective_timeout = timeout

    harnesses = _list_harnesses()

    if not harnesses:

        return {
            "success": False,
            "error": (
                "run_project_tests found no harnesses under "
                + "addons/Execution_Agent/tests."
            ),
        }

    results = []

    started = time.monotonic()

    for harness in harnesses:

        script_path = (
            "res://addons/Execution_Agent/tests/" + harness
        )

        command = [
            GODOT_BINARY_PATH,
            "--headless",
            "--path",
            PROJECT_PATH,
            "--script",
            script_path,
        ]

        harness_started = time.monotonic()

        try:

            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                errors="replace",
                timeout=effective_timeout,
            )

            exit_code = completed.returncode

            log = (completed.stdout or "") + (
                completed.stderr or ""
            )

        except subprocess.TimeoutExpired:

            results.append(
                {
                    "harness": harness,
                    "pass": False,
                    "exit_code": None,
                    "assertion_failures": 0,
                    "timed_out": True,
                    "detail": (
                        "timed out after "
                        + str(effective_timeout)
                        + " s"
                    ),
                }
            )

            continue

        duration_ms = round(
            (time.monotonic() - harness_started) * 1000,
            1,
        )

        assertion_failures = len(
            re.findall(r"Assertion failed", log)
        )

        passed = (
            exit_code == 0
            and assertion_failures == 0
        )

        detail = ""

        if not passed:

            error_lines = [
                line
                for line in log.splitlines()
                if "ERROR" in line or "Assertion" in line
            ]

            detail = " | ".join(error_lines[:3])[
                :MAX_LOG_CHARS
            ]

        results.append(
            {
                "harness": harness,
                "pass": passed,
                "exit_code": exit_code,
                "assertion_failures": assertion_failures,
                "timed_out": False,
                "duration_ms": duration_ms,
                "detail": detail,
            }
        )

    duration_s = round(time.monotonic() - started, 1)

    failed = [
        result
        for result in results
        if not result["pass"]
    ]

    return {
        "success": True,
        "action": "run_project_tests",
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed_count": len(failed),
        "all_passed": len(failed) == 0,
        "duration_s": duration_s,
        "results": results,
        "failed_harnesses": [
            result["harness"] for result in failed
        ],
    }

"""
Bridge-mode user input: lets the Godot editor panel drive the
agent instead of the terminal.

godot_agent.py reads user requests through read_user_request()
in agent/godot_agent.py; in bridge input mode (env
AGENT_INPUT_MODE=bridge) that function lands here and POLLS the
plugin's GET /agent_input route until the panel has a queued
request. The GET is deliberately consume-on-read: the plugin
hands the pending request over exactly once.

The same poll doubles as the agent-alive heartbeat - the plugin
records the poll time and the panel shows whether the agent
process is connected.

Strictly stdin-independent and never raises: if the bridge is
absent (editor closed), polling simply continues with a sleep,
so an operator can restart the editor without killing the agent.
"""

import json
import time
import urllib.request

from tools.scene_tools import GODOT_BRIDGE_URL


POLL_INTERVAL_SECONDS = 0.4

POLL_TIMEOUT_SECONDS = 2.0


def fetch_pending_input(
    bridge_url=None,
    timeout_seconds=None,
):
    """
    One consume-on-read GET /agent_input.

    Returns a dict:
        {"reachable": bool, "text": str, "mode": str,
         "selected_model": str, "selected_provider": str}

    mode is "plan" or "act" (the panel's toggle; empty
    string means the default, act). Never raises;
    unreachable bridges report reachable=False with empty
    fields.
    """

    url = (bridge_url or GODOT_BRIDGE_URL) + "/agent_input"

    effective_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else POLL_TIMEOUT_SECONDS
    )

    try:

        request = urllib.request.Request(
            url,
            headers={
                "Content-Type": "application/json"
            },
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=effective_timeout,
        ) as response:

            body = response.read().decode("utf-8")

        data = json.loads(body)

    except Exception:

        return {
            "reachable": False,
            "text": "",
            "mode": "",
            "selected_model": "",
            "selected_provider": "",
        }

    if not isinstance(data, dict):

        return {
            "reachable": False,
            "text": "",
            "mode": "",
            "selected_model": "",
            "selected_provider": "",
        }

    return {
        "reachable": True,
        "text": str(data.get("text", "") or ""),
        "mode": str(data.get("mode", "") or ""),
        "selected_model": str(
            data.get("selected_model", "") or ""
        ),
        "selected_provider": str(
            data.get("selected_provider", "") or ""
        ),
    }


def read_request(
    bridge_url=None,
    poll_interval=None,
    sleep=time.sleep,
):
    """
    Block until the panel has a queued request; returns it.

    `sleep` is injectable so tests can step through polling
    without real delays. Never raises.
    """

    interval = (
        poll_interval
        if poll_interval is not None
        else POLL_INTERVAL_SECONDS
    )

    while True:

        result = fetch_pending_input(bridge_url)

        if (
            result["reachable"]
            and result["text"].strip()
        ):

            return result

        sleep(interval)

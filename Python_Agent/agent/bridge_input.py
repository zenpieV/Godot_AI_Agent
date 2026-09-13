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
records the poll time and the panel shows whether the agent process
is connected.

Each poll identifies its own session (session_id query parameter).
When the bridge considers a DIFFERENT session active, it answers
superseded=True: read_request() then raises SessionSuperseded so an
older agent process terminates instead of racing the live session.
This is what makes every session start (START SESSION, New Session,
manual spawn) authoritative over any stale process.

Strictly stdin-independent: if the bridge is absent (editor closed),
polling simply continues with a sleep, so an operator can restart the
editor without killing the agent.
"""

import json
import time
import urllib.parse
import urllib.request

from tools.scene_tools import GODOT_BRIDGE_URL


POLL_INTERVAL_SECONDS = 0.4

POLL_TIMEOUT_SECONDS = 2.0


class SessionSuperseded(Exception):
    """
    Raised by read_request() when the bridge reports that
    a NEWER agent session has claimed active status.

    This is how stale agent processes die: whenever a new
    session starts (START SESSION, New Session, a manually
    spawned agent), every older process still polling the
    bridge receives superseded=True on its next poll and
    must terminate instead of racing the live session for
    queued requests or pushing events into its UI.
    """


def fetch_pending_input(
    bridge_url=None,
    timeout_seconds=None,
    session_id=None,
):
    """
    One consume-on-read GET /agent_input.

    Returns a dict:
        {"reachable": bool, "text": str, "mode": str,
         "selected_model": str, "selected_provider": str,
         "superseded": bool}

    mode is "plan" or "act" (the panel's toggle; empty
    string means the default, act). Never raises;
    unreachable bridges report reachable=False with empty
    fields. When session_id is given, a bridge that
    considers a DIFFERENT session active responds with
    superseded=True and no consumable input.
    """

    url = (bridge_url or GODOT_BRIDGE_URL) + "/agent_input"

    if session_id:

        url = (
            url
            + "?session_id="
            + urllib.parse.quote(str(session_id))
        )

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
            "superseded": False,
        }

    if not isinstance(data, dict):

        return {
            "reachable": False,
            "text": "",
            "mode": "",
            "selected_model": "",
            "selected_provider": "",
            "superseded": False,
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
        "superseded": bool(
            data.get("superseded", False)
        ),
    }


def read_request(
    bridge_url=None,
    poll_interval=None,
    sleep=time.sleep,
    session_id=None,
):
    """
    Block until the panel has a queued request; returns it.

    `sleep` is injectable so tests can step through polling
    without real delays. Never raises EXCEPT
    SessionSuperseded, which propagates so the agent loop
    can terminate: a newer session has claimed the bridge.
    """

    interval = (
        poll_interval
        if poll_interval is not None
        else POLL_INTERVAL_SECONDS
    )

    while True:

        result = fetch_pending_input(
            bridge_url,
            session_id=session_id,
        )

        if result["superseded"]:

            raise SessionSuperseded(
                "a newer agent session is active on the "
                "bridge"
            )

        if (
            result["reachable"]
            and result["text"].strip()
        ):

            return result

        sleep(interval)


def fetch_approval(
    bridge_url=None,
    timeout_seconds=None,
    session_id=None,
):
    """
    One consume-on-read GET /agent_approval. Returns
    {"reachable", "pending", "approved"}. Never raises.

    session_id gates the poll to this session, mirroring
    the input poll: a superseded agent's approval poll
    must never consume the active session's decision.
    """

    url = (bridge_url or GODOT_BRIDGE_URL) + "/agent_approval"

    if session_id:

        url = (
            url
            + "?session_id="
            + urllib.parse.quote(str(session_id))
        )

    effective_timeout = (
        timeout_seconds
        if timeout_seconds is not None
        else POLL_TIMEOUT_SECONDS
    )

    try:

        request = urllib.request.Request(
            url,
            method="GET",
        )

        with urllib.request.urlopen(
            request,
            timeout=effective_timeout,
        ) as response:
            data = json.loads(response.read().decode("utf-8"))

    except Exception:
        return {
            "reachable": False,
            "pending": False,
            "approved": False,
        }

    if not isinstance(data, dict):
        return {
            "reachable": False,
            "pending": False,
            "approved": False,
        }

    return {
        "reachable": True,
        "pending": bool(data.get("pending", False)),
        "approved": bool(data.get("approved", False)),
    }
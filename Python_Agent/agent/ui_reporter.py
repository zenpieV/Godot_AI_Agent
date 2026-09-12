"""
UI event reporter: pushes agent-state events to the Godot
editor plugin's UI (bottom panel) over the existing bridge.

This is the Python->editor half of the observability UI. It is
strictly best-effort fire-and-forget:

- every send has a tiny timeout and swallows ALL errors (the
  bridge may be absent, headless, or busy; the agent loop must
  never fail or slow down because the UI is not listening),
- the reporter can be disabled entirely via AGENT_UI_EVENTS=0,

Event payloads are small flat JSON objects:
    {"event": "<type>", "ts": <unix seconds>, ...fields}
The Godot-side state store (ai_agent_state_store.gd) owns the
interpretation; this module only transports. Unknown fields and
unknown event types are tolerated there, so the two sides can
evolve independently.
"""

import json
import os
import time
import urllib.request

from tools.scene_tools import GODOT_BRIDGE_URL


DEFAULT_TIMEOUT_SECONDS = 1.0


class UiReporter:

    def __init__(
        self,
        enabled=None,
        bridge_url=None,
        timeout_seconds=None,
    ):
        if enabled is None:
            enabled = os.environ.get(
                "AGENT_UI_EVENTS", "1"
            ).strip().lower() not in (
                "0", "false", "off",
            )

        self.enabled = enabled

        self.bridge_url = (
            bridge_url or GODOT_BRIDGE_URL
        )

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else DEFAULT_TIMEOUT_SECONDS
        )

    def report(self, event_type, **fields):
        """
        Send one UI event. Returns True when the event
        was accepted by the bridge, False otherwise.
        Never raises.
        """

        if not self.enabled:
            return False

        payload = {
            "event": str(event_type),
            "ts": round(time.time(), 3),
        }

        payload.update(fields)

        return self._post(payload)

    def _post(self, payload):
        """
        One fire-and-forget POST to /agent_event.
        Separated from report() so tests can capture
        payloads without network I/O.
        """

        try:

            data = json.dumps(
                payload
            ).encode("utf-8")

            request = urllib.request.Request(
                self.bridge_url + "/agent_event",
                data=data,
                headers={
                    "Content-Type": (
                        "application/json"
                    )
                },
                method="POST",
            )

            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:

                response.read()

            return True

        except Exception:

            return False

"""
Tests for the UI event reporter (agent/ui_reporter.py).

The reporter is the Python->editor push channel for the agent
observability UI. Contract under test:

- report() builds a flat payload with an "event" type and a "ts"
  timestamp and posts it to the bridge's /agent_event route,
- disabled reporters do nothing,
- ALL network failures are swallowed (never raised) - the UI
  must never break or slow the agent loop,
- the bridge URL defaults to the shared scene_tools constant so
  GODOT_BRIDGE_URL override applies to UI events too.
"""

import json

import pytest

from agent import ui_reporter as ui_reporter_module
from agent.ui_reporter import UiReporter
from tools import scene_tools


def _capture_reporter(monkeypatch, status=200, fail=False):
    captured = []

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b"{}"

    def fake_urlopen(request, timeout=None):
        if fail:
            raise OSError("bridge down")
        captured.append(
            {
                "url": request.full_url,
                "data": json.loads(
                    request.data.decode("utf-8")
                ),
                "timeout": timeout,
                "method": request.method,
            }
        )
        return FakeResponse()

    monkeypatch.setattr(
        ui_reporter_module.urllib.request,
        "urlopen",
        fake_urlopen,
    )
    return captured


def test_report_posts_flat_event_payload(monkeypatch):
    captured = _capture_reporter(monkeypatch)
    reporter = UiReporter(
        enabled=True,
        bridge_url="http://127.0.0.1:9999",
    )

    sent = reporter.report(
        "tool_started",
        turn=2,
        step=3,
        action="rename_script",
    )

    assert sent is True
    assert len(captured) == 1
    call = captured[0]
    assert call["url"] == "http://127.0.0.1:9999/agent_event"
    assert call["method"] == "POST"
    assert call["timeout"] == reporter.timeout_seconds
    payload = call["data"]
    assert payload["event"] == "tool_started"
    assert payload["turn"] == 2
    assert payload["step"] == 3
    assert payload["action"] == "rename_script"
    assert isinstance(payload["ts"], float)


def test_disabled_reporter_never_posts(monkeypatch):
    captured = _capture_reporter(monkeypatch)
    reporter = UiReporter(enabled=False)

    assert reporter.report("session_started") is False
    assert captured == []


def test_network_failure_is_swallowed(monkeypatch):
    _capture_reporter(monkeypatch, fail=True)
    reporter = UiReporter(
        enabled=True,
        bridge_url="http://127.0.0.1:9999",
    )

    # Must return False, never raise.
    assert reporter.report("error", context="x") is False


def test_default_bridge_url_matches_scene_tools():
    reporter = UiReporter(enabled=True)
    assert reporter.bridge_url == scene_tools.GODOT_BRIDGE_URL
    assert reporter.bridge_url.endswith("/8081") or (
        reporter.bridge_url.startswith("http://127.0.0.1")
    )


def test_env_disable(monkeypatch):
    monkeypatch.setenv("AGENT_UI_EVENTS", "0")
    captured = _capture_reporter(monkeypatch)
    reporter = UiReporter()

    assert reporter.enabled is False
    assert reporter.report("session_started") is False
    assert captured == []


def test_bridge_url_constructor_override(monkeypatch):
    """The bridge URL is constructor-injectable so tests and
    isolated live-validation instances can target another
    editor without touching the shared constant."""
    captured = _capture_reporter(monkeypatch)
    reporter = UiReporter(
        enabled=True,
        bridge_url="http://127.0.0.1:8082",
    )

    assert reporter.report("session_started") is True
    assert captured[0]["url"] == (
        "http://127.0.0.1:8082/agent_event"
    )


def test_report_envelope_carries_session_id(monkeypatch):
    """Every event is stamped with the emitting process's
    session id so the editor-side store can discard events
    from a superseded (older) agent process."""
    captured = _capture_reporter(monkeypatch)
    reporter = UiReporter(
        enabled=True,
        bridge_url="http://127.0.0.1:9999",
    )
    reporter.session_id = "abc123"

    reporter.report("turn_started", turn=1)

    payload = captured[0]["data"]
    assert payload["session_id"] == "abc123"
    assert payload["event"] == "turn_started"

    reporter.session_id = ""
    captured.clear()
    reporter.report("turn_started", turn=1)

    assert captured[0]["data"]["session_id"] == ""

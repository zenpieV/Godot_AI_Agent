# Godot AI Agent

An autonomous AI agent that operates inside the Godot editor: it reads natural-language requests, plans multi-step work, and executes real editor operations through a controlled, verified tool layer — while you watch (and steer) from a chat panel.

Python handles the agent reasoning and model-provider integration; a Godot EditorPlugin exposes a local HTTP bridge and the editor-native tools the agent is allowed to use.

## Features

- 74 registered actions across scene, node, property, script, scene-file, runtime, refactor, resource-file, and checkpoint domains — every mutation verified by read-back and recorded in a mutation ledger
- Chat-first editor panel: requests in, thinking stream and answers out, plan/act modes, model selector, approval gates for mutations, New Session respawn
- Session isolation: every session start is authoritative — stale agent processes are superseded and reap themselves; no context leaks between sessions
- Multi-provider: Gemini, Z.ai, Groq, OpenRouter, and Ollama (local), switchable per turn; uniform structured-output validation and transient-error retry
- Context compaction, batch execution with stop-on-failure boundaries, checkpoints, and headless self-tests (`run_project_tests`)

## Requirements

- **Windows** (the session launcher is Windows-specific)
- **Godot 4.7.2**
- **Python 3.10+** (the `py` launcher from python.org)

## Setup

1. Clone (or copy) this repository.
2. Install the Python dependencies:
   ```
   py -m pip install -r Python_Agent/requirements.txt
   ```
3. Create `Python_Agent/.env` with at least one provider key, e.g.:
   ```
   GEMINI_API_KEY=your_key_here
   ```
4. Open the project in Godot. The **AI Agent** panel appears at the bottom of the editor.
5. Press **START SESSION** — a console window opens (that is the agent's log; keep it open). Type a request in the chat and go.

Everything runs locally: the bridge listens on `127.0.0.1:8081` only, and the only external traffic is the model API calls made with your own keys.

## Architecture

- `addons/Execution_Agent/` — the EditorPlugin: HTTP bridge, action router, tool implementations (scene, node, property, script, scene-file, runtime, refactor, resource-file, checkpoint tools), and the chat panel
- `Python_Agent/` — the agent: conversation loop, provider adapters, action registry and schemas, batch/boundary enforcement, mutation contract, telemetry, and the headless test harness runner

The agent never touches the editor directly: every action is validated against a schema, classified as read-only or mutation, gated by the approval mode, executed by the plugin, and verified before its result is reported back.

## Documentation

Detailed and current docs live in `Python_Agent/docs/`:

- `TOOL_PROTOCOL.md` — every action, request/response shapes, verification fields
- `CURRENT_STATE.md` — implementation status
- `TEST_HISTORY.md` — what has been tested and validated, including known limitations
- `ROADMAP.md`, `PROVIDER_ARCHITECTURE.md`, `AGENT_HANDOFF.md`

## Tests

- Python: `py -m pytest tests/` from `Python_Agent/`
- Godot harnesses: the agent's own `run_project_tests` action, or any harness directly:
  ```
  Godot_v4.7.2-stable_win64_console.exe --headless --path . --script res://addons/Execution_Agent/tests/property_tools_harness.gd
  ```

## Status

Actively developed. Public version: session isolation, verified file management, model-selection passthrough, and the panel UX described above. See `Python_Agent/docs/ROADMAP.md` for what is next.

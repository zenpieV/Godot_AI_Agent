# Godot AI Agent

An autonomous AI assistant for Godot that can understand and interact with the editor, with Python handling the AI side and a Godot plugin handling editor operations.

## Project Structure

- `Python_Agent/` - Python agent logic, model providers, tools, tests, and documentation
- `addons/Execution_Agent/` - Godot EditorPlugin and editor-side bridge/tools
- `godot_bridge.gd` - Godot-side bridge used by the agent

## Current Architecture

The project is split into two main parts:

### Python Agent

Handles:

- Agent reasoning and decisions
- Model/provider integration
- Tool dispatch
- Agent sessions
- Action validation and safety boundaries
- Context management
- Tests

Gemini is currently the primary cloud model, with Ollama/Qwen available for local inference.

### Godot Plugin

Handles:

- Communication with the Python agent
- Scene inspection
- Node operations
- Property operations
- Editor-native changes
- Undo/redo integration

## Documentation

Project documentation is located in:

`Python_Agent/docs/`

Important documents include:

- `CURRENT_STATE.md`
- `AGENT_HANDOFF.md`
- `PROVIDER_ARCHITECTURE.md`
- `TOOL_PROTOCOL.md`
- `ROADMAP.md`
- `TEST_HISTORY.md`

## Status

This project is actively being developed toward an autonomous AI assistant that can safely operate inside the Godot Editor.
# AGENTS.md

## Repository Purpose

This repository contains the development of an AI-powered Godot Editor agent and plugin.

The long-term goal is to build a capable, reliable AI assistant that can understand natural-language requests and safely operate on a Godot project through native editor operations.

The intended end product is not merely a chatbot that can describe Godot concepts.

It is an agentic development system that can:

* Understand natural-language instructions from the developer.
* Inspect the current Godot project and scene state.
* Reason about multi-step tasks.
* Choose appropriate editor-native operations.
* Execute those operations through a controlled tool layer.
* Observe tool results.
* Recover from failures.
* Continue iterative workflows until the requested task is complete.
* Clearly report what happened.

The architecture must support progressively stronger AI models and providers while keeping the Godot execution layer safe and independent from any specific model provider.

The current project uses Python for agent reasoning and model-provider integration, while Godot provides editor-native operations through an EditorPlugin and a controlled HTTP bridge.

---

# Important Repository Context

Before making changes, read the applicable files below.

## Always-On Development Rules

These files contain persistent architectural and behavioral rules.

text
.agentrules/rules/01-DEVELOPMENT_RULES.md
.agentrules/rules/02-PROJECT_ARCHITECTURE.md


These rules should be treated as the default constraints for all development work.

---

## Dynamic Project State

These files contain frequently changing project information.

Read them when the task requires knowledge of the current implementation, previous testing, or planned development work.

```text
docs/CURRENT_STATE.md
docs/TEST_HISTORY.md
docs/ROADMAP.md
docs/TOOL_PROTOCOL.md
```

Do not assume these documents are permanently correct without checking the current source code when modifying existing behavior.

The source code is the ultimate authority for implementation details.

---

# Core Architectural Principle

The project separates AI reasoning from Godot execution.

## Python Layer

Python is responsible for:

* Receiving user requests.
* Managing agent iteration.
* Selecting and communicating with AI model providers.
* Parsing structured model decisions.
* Validating decisions.
* Applying deterministic safety and constraint repairs where appropriate.
* Sending tool requests to the Godot bridge.
* Receiving structured tool results.
* Feeding observations back into the reasoning loop.
* Producing the final user-facing response.

The Python layer must not depend on one specific AI provider.

The architecture should support multiple providers through a clean abstraction layer.

Current and planned provider categories include:

* Gemini for fast cloud reasoning.
* Groq-hosted models for high-speed inference and experimentation.
* Ollama for local inference and offline/private workflows.
* Potential future providers and models without requiring major changes to agent orchestration.

---

## Godot Layer

Godot is responsible for editor-native operations.

The Godot EditorPlugin should:

* Inspect the currently active scene.
* Traverse the scene tree.
* Locate nodes.
* Create nodes.
* Rename nodes.
* Reparent nodes.
* Modify supported properties.
* Eventually perform additional editor-native operations.

Operations should be performed using Godot's editor APIs rather than simulated GUI automation.

The Godot layer should remain authoritative regarding the actual editor state.

---

# Safety Requirements

The eventual agent must be:

* Safe.
* Observable.
* Undoable where Godot supports undo.
* Logged.
* Deterministic in its execution behavior.
* Explicit about failures.

The AI model may reason about what should happen.

The execution layer must validate what is allowed to happen.

Never rely solely on an AI model to guarantee correctness.

Important principles include:

1. Validate tool arguments before execution.
2. Return structured success and failure responses.
3. Preserve enough information to understand what happened.
4. Prefer editor-native undoable operations.
5. Avoid destructive actions without clear validation and future confirmation mechanisms.
6. Separate reasoning from execution.
7. Treat model output as untrusted structured input.
8. Avoid silently inventing scene paths or project state.
9. Prefer inspection before mutation when the required state is uncertain.
10. Make failures useful observations for the next reasoning step.

---

# Agent Behavior

The current agent operates iteratively.

A typical loop is:

```text
User Request
    ↓
Model Reasoning
    ↓
Structured Agent Decision
    ↓
Validation / Constraint Repair
    ↓
Godot Tool Execution
    ↓
Structured Tool Result
    ↓
Model Observes Result
    ↓
Next Decision
```

The loop ends when:

* The requested task has been completed and the model produces a valid final answer.
* The agent determines that the task cannot be completed.
* A safety or execution limit is reached.
* A deterministic system-level failure requires termination.

Multi-step tasks are expected and supported.

The agent should not be artificially designed around one-tool execution.

---

# Current Development Philosophy

Development must proceed incrementally.

When changing behavior:

1. Understand the current implementation.
2. Identify the actual failure mode or limitation.
3. Make the smallest coherent architectural change.
4. Test the change.
5. Inspect the logs and agent behavior.
6. Update dynamic project documentation when the behavior materially changes.

Do not perform broad speculative rewrites.

Do not replace working architecture merely because a model produced a theoretically cleaner design.

Preserve tested behavior whenever possible.

---

# Model Provider Strategy

Model providers are interchangeable reasoning backends.

The core agent loop should not contain provider-specific logic beyond a clean provider interface.

Provider-specific code should handle:

* Authentication.
* API requests.
* Model configuration.
* Response extraction.
* Structured output handling.
* Provider-specific errors.

The agent should receive a normalized response regardless of provider.

The architecture should eventually support:

```text
Agent
  ↓
Model Provider Interface
  ├── Gemini Provider
  ├── Groq Provider
  ├── Ollama Provider
  └── Future Providers
```

Provider integration should not require rewriting Godot tools.

---

# Ultimate Product Direction

The current implementation is an early foundation.

The ultimate objective is a highly capable Godot development agent that can operate as an intelligent development assistant inside or alongside the Godot Editor.

Over time, the agent should be able to perform increasingly sophisticated workflows such as:

* Inspecting scene structures.
* Creating and organizing node hierarchies.
* Renaming and restructuring existing scenes.
* Editing node properties.
* Creating reusable scene components.
* Assisting with scripts.
* Understanding relationships between scenes and resources.
* Diagnosing project and editor errors.
* Performing multi-step development tasks.
* Planning changes before execution.
* Observing results and correcting failed approaches.
* Eventually supporting larger autonomous or semi-autonomous development workflows.

The system should remain developer-controlled.

The goal is not uncontrolled autonomy.

The goal is useful autonomy with observability, validation, undoability, and clear boundaries.

---

# Important Development Rule

Do not confuse model intelligence with system reliability.

A stronger model may improve planning and reasoning, but the reliability of the product must primarily come from:

* Good tool design.
* Clear schemas.
* Deterministic validation.
* State inspection.
* Structured observations.
* Provider abstraction.
* Safe execution.
* Logging.
* Undo support.
* Incremental testing.

A capable model operating against poorly designed tools is still capable of making mistakes faster.

Build the system so that stronger models improve the agent without making weaker models unusable.

---

# Documentation Maintenance

When completing a meaningful implementation or test milestone:

* Update `docs/CURRENT_STATE.md` when the current architecture changes.
* Update `docs/TEST_HISTORY.md` when significant tests are run.
* Update `docs/ROADMAP.md` when development priorities change.
* Update `docs/TOOL_PROTOCOL.md` when tool request or response schemas change.

Do not update documentation speculatively.

Documentation should reflect tested or intentionally implemented behavior.

---

## Project State and Development Progress

The current implementation state, recent test results, active bugs, and
immediate development priorities are intentionally maintained outside this
file because they change frequently.

Before planning or implementing a feature, consult the relevant dynamic
project documents:

- `docs/CURRENT_STATE.md` for the current working implementation and known
  issues.
- `docs/TEST_HISTORY.md` for verified behavior and observed failures.
- `docs/ROADMAP.md` for development priorities and planned milestones.
- `docs/TOOL_PROTOCOL.md` when modifying or adding agent actions, Python
  bridge behavior, or Godot EditorPlugin operations.

Do not assume that the implementation state described elsewhere in the
repository is current if these documents provide more recent information.

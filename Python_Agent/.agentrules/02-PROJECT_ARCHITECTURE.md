# Project Architecture

## 1. Project Purpose and Ultimate Goal

Godot AI Agent is being developed as an AI-powered assistant for the Godot Editor.

The ultimate goal is to create a reliable AI agent capable of receiving natural-language development requests and safely performing meaningful Godot Editor operations.

The intended long-term system should allow a developer to express requests such as:

* Create and organize scene nodes.
* Inspect scene hierarchies.
* Search for nodes and resources.
* Rename and reparent nodes.
* Modify supported node properties.
* Create and modify project assets.
* Assist with scene construction.
* Assist with scripting and development workflows.
* Inspect project state before making changes.
* Recover intelligently from failed operations.
* Use multiple AI model providers.
* Select or route work to appropriate model providers.
* Prefer faster or cheaper models for simple operations.
* Use stronger models for difficult reasoning or complex development tasks.
* Support local inference where appropriate.
* Keep editor operations observable, safe, undoable where possible, and logged.

The project is not intended to be a one-shot code generator.

It is intended to become an iterative agent that can:

1. Observe the current Godot state.
2. Reason about the user's request.
3. Choose an appropriate action.
4. Execute an editor-native operation.
5. Observe the result.
6. Recover from failures when appropriate.
7. Continue iterating until the task is completed or cannot safely proceed.
8. Report the result clearly.

The current implementation is only an early foundation toward this larger goal.

Current implementation status belongs in `docs/CURRENT_STATE.md`, not in this architecture document.

---

# 2. High-Level System Architecture

The system consists of two primary components.

```text
┌─────────────────────────────────────────────┐
│ Python AI Agent                            │
│                                             │
│ - Agent reasoning loop                      │
│ - Provider abstraction                      │
│ - Gemini provider                           │
│ - Groq provider                             │
│ - OpenRouter provider                       │
│ - Ollama/local inference support            │
│ - Structured decisions                      │
│ - Validation and constraint repair          │
│ - Tool orchestration                        │
│ - Failure recovery                          │
└──────────────────────┬──────────────────────┘
                       │
                       │ Structured bridge
                       │
                       ▼
┌─────────────────────────────────────────────┐
│ Godot Editor Plugin                         │
│                                             │
│ - EditorPlugin integration                  │
│ - Scene inspection                          │
│ - Node discovery                            │
│ - Editor-native modifications               │
│ - Undo/redo integration                     │
│ - Structured tool responses                 │
│ - Future editor UI                          │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│ Active Godot Project                        │
│                                             │
│ - Current project                           │
│ - Currently edited scene                    │
│ - Scene tree                                │
│ - Nodes and supported resources             │
└─────────────────────────────────────────────┘
```

The Python agent and the Godot plugin are separate components of one system.

Changes to one side may affect the communication contract or behavior of the other side.

Do not treat them as unrelated projects.

---

# 3. Python Agent Repository

The Python repository is the AI reasoning and orchestration side of the system.

Conceptually:

```text
Agent_Host/
│
├── Python_Agent/
│   ├── AGENTS.md
│   │
│   ├── agent/
│   │   ├── godot_agent.py
│   │   ├── boundary.py
│   │   ├── schemas.py
│   │   ├── telemetry.py
│   │   └── ...
│   │
│   ├── models/
│   │   ├── gemini_provider.py
│   │   ├── groq_provider.py
│   │   ├── ollama_provider.py
│   │   ├── openrouter_provider.py
│   │   └── ...
│   │
│   ├── tools/
│   │   └── scene_tools.py
│   │
│   ├── config/
│   │   └── settings.py
│   │
│   ├── tests/
│   ├── docs/
│   └── .agentrules/
│       ├── 01-DEVELOPMENT_RULES.md
│       └── 02-PROJECT_ARCHITECTURE.md
```

The exact file structure may evolve.

Do not assume this conceptual tree is a complete or authoritative file listing.

Inspect the actual repository before modifying files.

The Python side is responsible for:

* Receiving user requests.
* Maintaining the iterative agent loop.
* Calling model providers.
* Parsing structured model decisions.
* Validating decisions.
* Applying deterministic constraint repair where appropriate.
* Calling Godot tools through the bridge.
* Feeding tool observations back into the reasoning loop.
* Detecting completion.
* Producing the final response.

The Python agent must not directly assume internal Godot editor state.

Godot state should be obtained through structured observations and tool responses.

---

# 4. Model Provider Architecture

The system should evolve toward a provider abstraction rather than hard-coding the agent around a single model vendor.

The intended provider ecosystem includes:

* Gemini as the current primary fast cloud model provider.
* Groq as an implemented high-speed cloud inference provider.
* OpenRouter as an implemented additional cloud provider entry point.
* Ollama for local inference.
* Qwen models where appropriate through local or supported providers.
* Potential future stronger cloud providers.

The provider layer should eventually allow the agent architecture to remain stable while providers change.

Provider-specific SDK logic should not spread through unrelated agent logic.

Prefer an architecture conceptually similar to:

```text
Agent
  │
  ▼
Provider abstraction
  │
  ├── Gemini provider
  ├── Groq provider
  ├── OpenRouter provider
  ├── Ollama provider
  └── Future providers
```

Model selection, routing, fallback behavior, and provider capabilities should be developed incrementally.

Do not prematurely redesign the entire agent around hypothetical providers.

Preserve working behavior while adding abstractions.

---

# 5. Godot Editor Plugin

The Godot plugin is responsible for operations that must occur inside the Godot Editor.

Its current location within the host project is:

```text
res://addons/Execution_Agent/
```

Conceptually:

```text
addons/
└── Execution_Agent/
    ├── plugin.cfg
    ├── ai_agent_plugin.gd
    ├── bridge/
    ├── scene/
    ├── serialization/
    └── additional plugin files
```

The plugin should be portable between Godot projects.

It must not depend on:

* The disposable development project's scene names.
* Specific game assets.
* Specific test nodes.
* Hard-coded project scene paths.
* Hard-coded gameplay structures.

For example, plugin logic should not assume that a node such as `CharacterBody2D` always exists.

The plugin should operate on actual editor state and actual scene data.

The disposable Godot project is a development and testing host.

It is not the product.

---

# 6. Unified Host Project Architecture

The Python agent package and the Godot host project are now colocated under a single unified workspace root.

The current merged structure is:

```text
Agent_Host/                    ← workspace root
│
├── Python_Agent/              ← Python agent package
│   └── (agent loop, providers, tools, config, tests, docs)
│
├── addons/
│   └── Execution_Agent/       ← Godot EditorPlugin
│
├── godot_bridge.gd
├── game_scene.tscn
├── project.godot
└── icon.svg
```

The two halves communicate over a local HTTP bridge:

- The EditorPlugin (`addons/Execution_Agent/`) listens on `http://127.0.0.1:8081`
- The runtime scene bridge (`godot_bridge.gd`) listens on `http://127.0.0.1:8080`
- The Python agent (`Python_Agent/tools/scene_tools.py`) talks to the editor bridge at `http://127.0.0.1:8081`

Before modifying cross-component behavior:

1. Inspect the relevant files on both sides.
2. Identify the communication contract.
3. Determine whether changes remain compatible.
4. Update both sides when the contract requires it.
5. Report all affected files.

Do not assume that a file exists at a relative path from another workspace root.

Use the actual workspace structure visible to the IDE.

---

# 7. Disposable Development Host vs Portable Plugin

The current Godot project used for development is intentionally disposable.

Its purpose includes:

* Developing the plugin.
* Testing scene operations.
* Testing success cases.
* Testing failure cases.
* Testing recovery behavior.
* Testing undoable editor operations.
* Performing regression testing.

The development project may contain temporary nodes and test data.

Examples may include nodes created solely for testing operations.

Those test nodes are not part of the plugin architecture.

The portable plugin must eventually work when copied into a completely different Godot project.

A future portability milestone should test:

1. Create a fresh Godot project.
2. Copy only the plugin into its `addons` directory.
3. Enable the plugin.
4. Connect it to the Python agent.
5. Open or create an arbitrary scene.
6. Perform scene inspection.
7. Perform supported editor operations.
8. Test failure handling.
9. Test undo/redo behavior where supported.

Success in the disposable project alone does not prove portability.

---

# 8. Python-to-Godot Bridge

The Python agent communicates with the Godot Editor through a structured bridge.

The bridge is a critical architectural boundary.

The Python agent should not depend on undocumented assumptions about Godot internals.

The Godot plugin should return structured observations describing:

* Success or failure.
* Relevant error information.
* Relevant node paths.
* Created or modified entities where applicable.
* Whether an operation is undoable where applicable.
* Structured scene data where applicable.

The Python side should interpret those responses deterministically.

The detailed tool contracts belong in:

```text
docs/TOOL_PROTOCOL.md
```

That file is the authoritative place for documenting expected request and response structures.

When changing a tool contract:

1. Inspect the current implementation.
2. Update both sides if required.
3. Update `docs/TOOL_PROTOCOL.md`.
4. Preserve backward compatibility where practical.
5. Add or update tests.

Do not silently change payload semantics.

---

# 9. Agent Reasoning Loop

The intended agent architecture is iterative.

Conceptually:

```text
User request
    │
    ▼
Model reasoning
    │
    ▼
Structured decision
    │
    ▼
Validation / constraint repair
    │
    ▼
Godot tool execution
    │
    ▼
Structured observation
    │
    ├── Success → continue or finalize
    │
    └── Failure → reason again when appropriate
```

The agent should not assume that one model response is sufficient to complete a task.

The model may need to:

* Search for nodes.
* Inspect the scene tree.
* Resolve paths.
* Retry with corrected arguments.
* Recover from failed operations.
* Decide that the task cannot proceed.

However, the agent should also avoid pointless repeated retries.

Repeated failures with the same cause should be detected and handled deliberately.

---

# 10. Safety and Editor Operations

The system should evolve toward editor operations that are:

* Observable.
* Explicit.
* Structured.
* Logged.
* Undoable where supported by Godot.
* Validated before execution where practical.

The Godot plugin should prefer editor-native APIs and undo/redo mechanisms rather than directly mutating project files when editor-native operations are appropriate.

Do not introduce destructive behavior without understanding how it can be observed, validated, and recovered.

Future operations may require additional safeguards such as:

* Confirmation policies.
* Dry-run or preview modes.
* Operation logs.
* Reversible action groups.
* Explicit destructive-operation handling.

These should be added incrementally when the relevant functionality is introduced.

---

# 11. State and Documentation Responsibilities

The architecture document describes stable system structure.

Dynamic information belongs elsewhere.

Use:

```text
docs/CURRENT_STATE.md
```

for:

* Current implementation status.
* Recent completed work.
* Current known issues.
* Immediate next development focus.

Use:

```text
docs/TEST_HISTORY.md
```

for:

* Tests performed.
* Successful behavior.
* Failures discovered.
* Regression information.

Use:

```text
docs/ROADMAP.md
```

for:

* Planned future work.
* Development phases.
* Major milestones.

Use:

```text
docs/TOOL_PROTOCOL.md
```

for:

* Tool definitions.
* Request parameters.
* Response payload structures.
* Tool semantics.
* Error behavior.

Do not place temporary implementation status into static architecture rules.

---

# 12. IDE Agent Role

The IDE agent is primarily an implementation agent with direct repository access.

The preferred development workflow is:

```text
Discussion and planning
        ↓
Implementation prompt
        ↓
IDE agent inspects relevant files
        ↓
IDE agent modifies code
        ↓
IDE agent validates where possible
        ↓
User performs required runtime tests
        ↓
Implementation/test report
        ↓
Architecture and debugging review
        ↓
Next implementation step
```

The IDE agent should not blindly modify files based solely on a prompt when the actual repository state can be inspected.

Before making changes, it should inspect relevant existing files.

After making changes, it should report:

```text
IMPLEMENTATION REPORT

1. Files inspected
2. Files modified
3. What changed in each file
4. Validation performed
5. Current behavior
6. Known limitations or unresolved issues
7. Exact tests the user should run next
```

The report should describe actual work performed.

Do not claim tests passed unless they were actually run.

---

# 13. Architectural Principles

The system should evolve according to these principles:

* Preserve working behavior.
* Prefer incremental changes.
* Inspect before modifying.
* Debug causes instead of patching symptoms.
* Keep provider logic separated from core agent logic.
* Keep Python reasoning separated from Godot editor-native operations.
* Use structured tool contracts.
* Treat tool failures as observations for the reasoning loop.
* Avoid hard-coded assumptions about individual Godot projects.
* Preserve plugin portability.
* Prefer editor-native and undoable operations.
* Make significant behavior observable and eventually logged.
* Avoid unnecessary rewrites.
* Do not expand architecture prematurely without evidence that the current structure requires it.

When uncertain, inspect the current implementation and documentation before changing architecture.

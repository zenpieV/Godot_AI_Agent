# Godot AI Agent Roadmap

## Purpose

This roadmap tracks the planned development direction of the Godot AI Agent.

The ultimate goal is to build a capable AI agent that can understand natural-language requests, reason through multi-step tasks, inspect the current Godot editor state, safely perform editor-native operations, observe results, recover from failures, and eventually assist with substantial Godot project development.

The agent is intended to become more than a command-to-function translator.

Its long-term behavior should resemble an iterative development assistant:

1. Receive a natural-language request.
2. Inspect the relevant project or scene state.
3. Decide what information is missing.
4. Perform one safe editor-native operation at a time.
5. Observe structured results.
6. Update its reasoning using those results.
7. Recover from failures when possible.
8. Verify important changes.
9. Produce a clear final result.

The system should remain safe, observable, undoable where possible, and logged.

---

# Development Principles

The roadmap should be followed incrementally.

Do not attempt to implement multiple major architectural stages in one change unless explicitly requested.

For every new capability:

1. Understand the existing implementation.
2. Identify the smallest safe change.
3. Implement the change.
4. Run relevant tests.
5. Inspect failures.
6. Fix the underlying cause rather than masking symptoms.
7. Update dynamic project documentation when the change is confirmed.

Static architecture rules belong in:

- `.agentrules/rules/01-DEVELOPMENT_RULES.md`
- `.agentrules/rules/02-PROJECT_ARCHITECTURE.md`

Current implementation state belongs in:

- `docs/CURRENT_STATE.md`

Historical verified behavior belongs in:

- `docs/TEST_HISTORY.md`

This roadmap describes direction and priorities rather than acting as a record of the current implementation state.

---

# Phase 1: Stabilize the Existing Agent Foundation

## Goal

Make the existing Python reasoning loop and Godot editor bridge reliable before adding large numbers of new tools.

The current foundation already demonstrates that the agent can perform iterative reasoning and recover from some failed operations.

The priority is now reducing unnecessary failures and making tool semantics deterministic.

## Work Items

### 1.1 Improve Decision Validation

The agent should validate structured decisions before executing them.

Examples:

- `create_node` requires:
  - `parent_path`
  - `node_type`
  - `node_name`

- `rename_node` requires:
  - `node_path`
  - `new_name`

- `reparent_node` requires:
  - `node_path`
  - `new_parent_path`

When required information is missing, the system should prefer deterministic recovery behavior instead of blindly executing an invalid tool call.

Possible strategies include:

- infer only when the inference is unambiguous,
- search for explicitly named nodes,
- ask the model to reason again using the observed tool failure,
- reject malformed decisions before the Godot bridge is contacted.

---

### 1.2 Stabilize Constraint Repair

Constraint repair must help the model without accidentally changing the meaning of its intended operation.

A previous issue demonstrated that a destination parent mentioned in a reparenting request was incorrectly injected as a `find_nodes.parent_path` search scope.

The desired rule is:

- A parent mentioned as an operation destination should not automatically become a search scope.
- A parent explicitly requested as a search scope may be used as `find_nodes.parent_path`.
- Searching for the destination node itself should normally occur across the whole scene unless a scope is explicitly required.

Constraint repair should be conservative.

It should repair obvious structural omissions, not reinterpret every user noun as a tool parameter.

---

### 1.3 Improve Tool Result Awareness

The model should receive useful structured observations after every tool call.

Tool results should clearly communicate:

- success or failure,
- the action performed,
- resolved paths,
- created paths,
- old and new names,
- parent paths,
- error messages,
- whether the operation was undoable.

The agent should use these observations to guide the next step rather than repeating failed actions.

---

### 1.4 Reduce Repeated Invalid Steps

The agent should avoid loops such as:

1. make malformed call,
2. receive explicit validation error,
3. make the same malformed call again.

Potential improvements may include deterministic validation before execution or feeding stronger structured failure context into the next reasoning step.

The exact implementation should be chosen after inspecting the current code.

---

### 1.5 Review MAX_STEPS Behavior

The agent must have a configurable maximum iteration count.

The limit should:

- allow realistic multi-step recovery,
- prevent infinite loops,
- produce a useful failure response if exhausted,
- be easy to configure.

Do not arbitrarily increase the limit without understanding why additional steps are needed.

Long task completion should come primarily from efficient reasoning and reliable tools rather than simply giving the model more chances to wander through the forest.

---

# Phase 2: Provider Abstraction

## Goal

Decouple agent reasoning from any single model provider.

The project currently uses Gemini as the primary fast cloud model and keeps Ollama/Qwen available for local inference.

Groq is planned as an additional provider.

The provider architecture should make it possible to switch reasoning backends without rewriting agent logic.

---

## Work Items

### 2.1 Define a Provider Interface

Create a clear abstraction around model providers.

The agent loop should request a structured decision from a provider without needing provider-specific code throughout the reasoning loop.

Conceptually, the agent should depend on something similar to:

- request structured decision,
- receive model output,
- parse decision,
- return normalized result.

The exact class or function structure should follow the existing project architecture.

---

### 2.2 Gemini Provider

Preserve Gemini support as the primary fast cloud reasoning provider.

The current Gemini implementation should be examined for:

- structured output reliability,
- warnings related to automatic function calling,
- maintainability,
- error handling.

The warning about direct automatic function calling should eventually be addressed deliberately rather than ignored forever.

Do not refactor Gemini blindly while the current system is functioning.

---

### 2.3 Ollama Provider

Preserve local inference support.

Ollama should remain useful for:

- experimentation,
- offline or local workflows,
- testing provider abstraction,
- users who prefer local models.

The provider interface should not assume cloud-only behavior.

---

### 2.4 Groq Provider

Integrate Groq through the same provider abstraction rather than embedding Groq-specific logic directly into the agent loop.

Potential models should be evaluated based on:

- structured reasoning reliability,
- JSON generation quality,
- latency,
- cost or free-tier availability,
- ability to follow multi-step agent context.

The first implementation should focus on reliable structured decisions rather than adding multiple Groq models simultaneously.

---

### 2.5 Provider Configuration

Model provider configuration should eventually be explicit and centralized.

Potential configuration includes:

- active provider,
- active model,
- API credentials loaded from environment variables,
- local endpoint configuration,
- fallback behavior.

Secrets must not be committed to the repository.

---

# Phase 3: Expand Godot Editor Operations

## Goal

Gradually expand the Godot EditorPlugin capabilities beyond basic scene-tree manipulation.

Every new operation should remain:

- editor-native,
- observable,
- structured,
- safe,
- undoable where Godot supports undo/redo integration.

---

## Candidate Operations

### Scene Inspection

Expand inspection capabilities beyond the full scene tree.

Potential operations:

- inspect a specific node,
- inspect node properties,
- inspect node children,
- inspect attached scripts,
- inspect resource references.

---

### Node Operations

Potential additions:

- delete node,
- duplicate node,
- set node property,
- get node property,
- add child with additional configuration,
- move node among siblings,
- change ownership where required.

Destructive operations require particularly careful safety behavior.

---

### Property Editing

Eventually allow natural-language property changes such as:

- position,
- rotation,
- scale,
- visibility,
- texture assignments,
- collision settings.

The Python agent should not invent Godot property schemas.

Godot should remain the authoritative environment for validating actual node types and properties.

---

### Script Operations

Future capabilities may include:

- inspect attached scripts,
- create scripts,
- attach scripts,
- edit scripts through controlled workflows,
- inspect parser or compiler errors.

Script modification should eventually include verification steps.

---

### Scene Operations

Potential future capabilities:

- create scenes,
- save scenes,
- instantiate scenes,
- modify scene structure,
- inspect scene dependencies.

---

# Phase 4: Verification and Recovery

## Goal

Move from "tool call succeeded" toward "requested change was verified."

A successful HTTP response is not always equivalent to the desired project state.

---

## Verification Pattern

For important operations, the agent should eventually follow:

1. Inspect relevant state.
2. Perform operation.
3. Receive operation result.
4. Re-inspect relevant state.
5. Confirm the requested outcome.

Examples:

- after creating a node, verify that it exists,
- after renaming, verify the new path or name,
- after reparenting, verify the new hierarchy,
- after setting a property, verify the property value.

Verification should be used selectively to avoid unnecessary tool calls.

---

## Recovery Behavior

When an operation fails:

1. Read the structured error.
2. Determine whether the failure is recoverable.
3. Inspect missing information if needed.
4. Retry only when the new attempt is materially different.
5. Stop when recovery is not possible.

The agent should not repeatedly retry identical invalid requests.

---

# Phase 5: Logging and Observability

## Goal

Make agent behavior understandable and debuggable.

The system should eventually maintain structured records of:

- user request,
- agent step number,
- model decision,
- deterministic repairs,
- tool calls,
- tool results,
- failures,
- final answer.

Sensitive credentials must never appear in logs.

---

## Desired Logging Properties

Logs should eventually support answering questions such as:

- Why did the agent choose this action?
- What did the model originally return?
- What deterministic repair was applied?
- What did Godot report?
- Why did the agent retry?
- Why did the agent stop?

Observability is especially important as the number of tools and providers grows.

---

# Phase 6: Safety and Undoability

## Goal

Preserve the ability to safely experiment with AI-driven editor operations.

The preferred architecture is:

Natural-language request
→ agent reasoning
→ validated structured decision
→ Godot EditorPlugin operation
→ UndoRedo integration where possible
→ structured observation
→ optional verification

Destructive operations should eventually receive additional safeguards.

Potential future safeguards include:

- operation previews,
- confirmation requirements,
- change summaries,
- transaction grouping,
- automatic rollback when verification fails.

These should be introduced carefully rather than blocking basic development unnecessarily.

---

# Phase 7: Higher-Level Task Planning

## Goal

Allow the agent to solve larger Godot development tasks composed of multiple editor operations.

Examples could eventually include:

- create an enemy hierarchy,
- configure collision nodes,
- add sprites,
- attach scripts,
- configure properties,
- verify the resulting scene structure.

The agent should break larger requests into tool-observable steps.

Planning should remain grounded in the actual editor state.

The system should avoid generating a giant speculative plan and executing it blindly.

A stronger pattern is:

plan partially
→ inspect
→ act
→ observe
→ update plan
→ continue

---

# Phase 8: Project-Aware Development

## Goal

Eventually allow the agent to reason about more than the currently open scene.

Potential capabilities:

- inspect project structure,
- discover scenes,
- inspect scripts,
- understand project resources,
- identify relevant files,
- navigate dependencies.

The Godot editor and project filesystem should remain authoritative sources of state.

---

# Phase 9: User-Facing Godot Plugin Experience

## Goal

Move from command-line experimentation toward a polished Godot EditorPlugin experience.

Potential features include:

- editor dock or panel,
- natural-language input,
- visible agent progress,
- tool activity display,
- operation history,
- errors and recovery explanations,
- provider selection,
- configuration controls.

The user should be able to understand what the agent is doing rather than watching an invisible language model operate the editor like a haunted keyboard.

---

# Phase 10: Advanced Agent Capabilities

These are long-term directions rather than immediate implementation tasks.

Potential capabilities include:

- multi-scene reasoning,
- project-wide refactoring assistance,
- debugging assistance,
- error inspection,
- automated verification,
- scene generation,
- script generation and repair,
- resource configuration,
- gameplay system construction.

These capabilities should only be added after the lower-level tool foundation is reliable.

The project should not attempt to become an autonomous game studio before it can reliably find a node.

---

# Recommended Near-Term Priority

The next major development sequence should be:

1. Review and stabilize the existing `godot_agent.py` reasoning loop.
2. Improve malformed decision handling and deterministic validation.
3. Stabilize constraint-repair semantics.
4. Reduce repeated invalid tool calls.
5. Define and implement provider abstraction.
6. Add Groq through that abstraction.
7. Preserve Gemini and Ollama support.
8. Expand Godot operations gradually.
9. Add verification patterns.
10. Improve logging and observability.

The exact next implementation task must always be chosen using the current state in `docs/CURRENT_STATE.md`, recent verified results in `docs/TEST_HISTORY.md`, and this roadmap.

---

# Known Gaps and Remaining Work

## Completed Milestones

- Persistent in-memory multi-turn `AgentSession` with conversation and
  execution history retained across turns.
- Agent-controlled session termination via structured `exit_session`
  action (distinct from `final_answer` turn completion).
- Generator termination regression fix preventing model calls after
  session close.
- Two-tier batch safety boundary (exact fingerprint + mutation-target
  identity) with parameter-change bypass prevention.

## Documentation Gaps

- **Empty-input behavior**: Empty input at the `begin_next_turn()` prompt
  currently terminates the session silently (no log). This is
  inconsistent with `/exit` and should be addressed or at minimum
  documented as a deliberate behavior.
- **Live multi-turn contextual validation**: Historical live tests
  demonstrated that a later user request could rely on context from an
  earlier turn (e.g., creating limbs across turns with correct
  inference of existing nodes). This is not represented in repository
  documentation and should be recorded when re-validated.
- **Undo verification**: The expectation that editor mutations are
  undoable is documented architecturally but not yet covered by
  automated tests.

## Remaining Implementation Priorities

- Provider abstraction formalization and provider-contract test harness.
- Groq end-to-end validation.
- Expanded Godot operations (scripts, resources, project inspection).
- Session-summary/observability on termination.

---

# Documentation Maintenance Rules

When development progresses:

Update `docs/CURRENT_STATE.md` when:

- architecture changes,
- active capabilities change,
- the next implementation priority changes,
- provider support changes.

Update `docs/TEST_HISTORY.md` when:

- a test produces a verified result,
- a bug is reproduced,
- a bug is fixed and retested.

Update this `docs/ROADMAP.md` only when:

- priorities change substantially,
- a roadmap phase is completed,
- a major planned capability is added, removed, or reordered.

Do not treat the roadmap as a live implementation log.
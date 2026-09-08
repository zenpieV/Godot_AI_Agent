# Development Rules

## 1. Core Development Philosophy

This project must be developed incrementally, deliberately, and with observable behavior.

Do not make broad speculative changes across multiple systems when a smaller change can be implemented and verified first.

When modifying the project:

1. Understand the existing implementation.
2. Identify the actual cause of the problem or limitation.
3. Make the smallest coherent change that addresses it.
4. Preserve existing working behavior unless a deliberate redesign is intended.
5. Test the change.
6. Record important implementation or behavioral changes in the appropriate dynamic documentation.

Do not blindly replace working code with a theoretically cleaner implementation without understanding the existing behavior.

---

## 2. Debug Before Modifying

When a failure occurs, investigate before attempting a fix.

Use available evidence such as:

* Agent step logs.
* Raw model responses.
* Parsed agent decisions.
* Constraint-repair logs.
* Tool requests.
* Tool responses.
* Godot editor behavior.
* Python exceptions.
* HTTP bridge responses.
* Existing tests and test history.

Do not assume that the model is the source of a failure.

A failure may originate from:

* Model output.
* Structured decision parsing.
* Decision validation.
* Constraint repair.
* Agent-loop state handling.
* Tool dispatch.
* Python HTTP communication.
* Godot EditorPlugin behavior.
* Incorrect scene assumptions.
* Invalid node paths.
* Stale editor state.

Identify the layer responsible before changing code.

---

## 3. Preserve Architectural Boundaries

The project uses a deliberate separation between agent reasoning and Godot editor execution.

The general responsibility split is:

* The AI model reasons about the user's request and selects structured actions.
* Python manages agent reasoning, provider communication, validation, state, and tool orchestration.
* The Godot EditorPlugin performs editor-native operations.
* Communication between Python and Godot occurs through the project's defined bridge.

Do not move Godot editor-native responsibilities into Python merely because it is temporarily easier.

Do not move model reasoning into the Godot plugin.

Do not bypass established boundaries without a deliberate architectural change.

---

## 4. Prefer Structured Data Over Implicit Text Parsing

Communication between system layers should use structured data whenever practical.

Agent decisions, tool requests, tool results, and observations should remain machine-readable.

Prefer explicit fields over encoding operational information inside free-form strings.

For example, a node operation should represent relevant information through fields such as:

* Action.
* Node path.
* Parent path.
* New parent path.
* Node name.
* Node type.
* Properties.

Do not rely on parsing natural-language explanations when structured fields can represent the same information.

Natural-language reasoning is useful for explanation and debugging, but it must not become the primary transport format for editor operations.

---

## 5. Validate Before Executing

Model-generated decisions must not be assumed to be correct.

Before an editor operation is executed:

1. Parse the decision.
2. Validate the action.
3. Validate required fields.
4. Apply deterministic repairs only when the repair is clearly justified.
5. Reject unsafe or ambiguous requests.
6. Execute only after the request is sufficiently valid.

Deterministic validation and repair should improve reliability without silently inventing user intent.

A repair is acceptable only when the intended value is clearly supported by available context.

If the intended value cannot be determined reliably, request additional information through the agent workflow rather than guessing.

---

## 6. Tool Failures Are Observations, Not Automatic Termination

A failed tool operation should normally become information available to the agent.

The agent should be able to inspect structured failures and reason about recovery.

Examples include:

* A node was not found.
* A parent path was invalid.
* Required fields were missing.
* A node path changed after another operation.
* A requested operation is invalid in the current scene state.

Do not treat every tool failure as a fatal system error.

However, the agent must not retry the same invalid operation indefinitely.

Repeated failures should cause the agent to:

1. Inspect the failure.
2. Gather additional state if necessary.
3. Change strategy.
4. Stop with an honest explanation when recovery is not possible.

---

## 7. Prefer Observation Before Assumption

When the current Godot scene state matters, inspect it.

Do not assume:

* A node still exists.
* A node is at its previous path.
* A parent exists.
* A previous rename did not change a path.
* A previous reparent operation did not change hierarchy.
* The editor scene state matches an earlier observation.

Use scene inspection or node discovery when state must be verified.

Tool observations are authoritative only for the state at the time they were retrieved.

---

## 8. Operations Must Be Safe and Undoable When Possible

Editor modifications should preserve normal Godot editor behavior.

When Godot provides appropriate editor-native mechanisms for undoable operations, use them.

Prefer operations that:

* Can be undone through the editor.
* Preserve editor consistency.
* Avoid corrupting scene state.
* Produce observable results.
* Return structured success or failure information.

Do not directly mutate project or scene files when an appropriate editor-native operation exists, unless a deliberate architectural decision establishes otherwise.

---

## 9. Every Meaningful Operation Must Be Observable

The development architecture should make important behavior inspectable.

Where practical, log or expose:

* Agent steps.
* Raw provider responses.
* Parsed decisions.
* Validation or constraint repairs.
* Tool requests.
* Tool results.
* Errors.
* Recovery attempts.

Logs should help answer:

> What did the model decide?

> What did the agent actually execute?

> What happened inside the Godot editor?

Avoid silent transformations of model output.

If deterministic logic changes a decision, the change should be observable in debugging output.

---

## 10. Do Not Let the Model Directly Control Unsafe Editor Behavior

The AI model proposes structured actions.

The deterministic system remains responsible for deciding whether those actions are valid and executable.

Model output must not bypass:

* Validation.
* Required-field checks.
* Tool semantics.
* Editor safety constraints.
* Future permission systems.

The model is a reasoning component, not an unrestricted executor.

This principle becomes increasingly important as the project expands toward more powerful editor operations.

---

## 11. Preserve Provider Independence

The agent architecture must not become tightly coupled to one model provider.

Model providers may differ in:

* API structure.
* Response formats.
* Tool-calling capabilities.
* Context limits.
* Reliability.
* Latency.
* Cost.
* Local versus cloud execution.

Provider-specific behavior should remain isolated behind a provider abstraction wherever practical.

The rest of the agent should operate on normalized concepts such as:

* User request.
* Conversation context.
* Structured decision.
* Model response.
* Error.

---

## 12. Gemini Schema Regression Guard

When adding, removing, or reshaping an `AgentDecision` action, treat the
Gemini response schema as a compatibility boundary. Do not assume that a
Pydantic-valid discriminated union is accepted by Gemini after provider
normalization.

The known failure mode is:

1. Pydantic emits `oneOf`, `$ref`, and discriminator metadata.
2. The Gemini adapter removes the discriminator and converts `oneOf` to
   `anyOf`.
3. Structurally overlapping action branches, especially branches with the
	same optional fields or several no-parameter actions, cause Gemini to
	reject the entire request with `400 INVALID_ARGUMENT`.

Required workflow for every action-schema change:

1. Generate the exact `AgentDecision` schema used by `ask_model()`.
2. Pass it through `make_gemini_schema_compatible()`.
3. Inspect both the top-level action union and the nested `batch.actions`
   union for overlapping branches, stale `$ref` entries, `oneOf`, or
   `discriminator` keywords.
4. Run the focused provider adapter tests.
5. Run a real Gemini schema smoke test when credentials are available. If a
   live call returns `400 INVALID_ARGUMENT`, isolate the changed actions by
   removing them one at a time and as a group until the causal branch is
   proven.

The fix must remain provider-only. Preserve the public Pydantic action
schemas, Python registry dispatch, batch validation, and Godot tool
semantics. If Gemini cannot accept a branch inside a nested batch union,
exclude or transform that branch only in the Gemini adapter while retaining
the public contract. Add a regression assertion for the normalized schema
and do not declare the task complete based only on mocked SDK tests.

Before finalizing, verify at minimum:

```text
Python provider adapter tests pass
Full Python suite passes
Normalized Gemini schema contains no oneOf/discriminator
Changed actions are present where intended
No unintended branches remain in nested batch unions
```

Do not spread provider-specific implementation details throughout the agent loop.

---

## 12. Prefer Capability-Based Model Use

Different models may eventually be better suited for different tasks.

The architecture should allow future routing based on capabilities such as:

* Fast structured reasoning.
* Complex planning.
* Local/private inference.
* Low-latency interaction.
* Large-context analysis.
* Fallback availability.

Do not hard-code the assumption that one provider or model will always perform every role.

Model routing must remain observable and configurable.

---

## 13. Avoid Unnecessary Complexity

Do not introduce abstractions before they solve a real architectural problem.

Avoid adding:

* Frameworks.
* Background systems.
* Databases.
* Message queues.
* Provider layers.
* Caching layers.
* Permission systems.
* State machines.

unless they solve an identified requirement.

The project should grow in response to demonstrated needs.

A smaller system that is understood and tested is preferable to a theoretically sophisticated system whose behavior is unclear.

---

## 14. Prefer Complete File Replacements When They Reduce Human Error

When a change requires many scattered edits and providing a complete replacement file would reduce the risk of manual mistakes, prefer supplying the complete file.

When making a targeted change is genuinely simple and safe, provide the exact location and modification.

The priority is reducing accidental integration errors.

Do not fragment a coherent implementation into many tiny edits merely to minimize the amount of text changed.

---

## 15. State File Locations Explicitly

When providing implementation instructions, clearly state:

* The exact file path.
* Whether the file is new or existing.
* Whether the contents should replace the entire file.
* The purpose of the change.
* How the change connects to the surrounding architecture.

Avoid instructions such as:

> Add this somewhere near the agent loop.

Precise locations prevent human interpretation from becoming another runtime dependency.

---

## 16. Test Real Behavior, Not Just Code Paths

A feature is not considered sufficiently verified merely because:

* The code runs.
* The Python function returns.
* The model generated valid-looking JSON.

Verify the complete relevant path when possible.

For Godot operations, this generally means confirming:

1. The user request is understood.
2. The model produces a structured decision.
3. The decision is validated.
4. The correct tool is dispatched.
5. Python communicates correctly with Godot.
6. Godot performs the intended operation.
7. The resulting scene state is correct.
8. Failure behavior is also tested.

Test both successful and unsuccessful scenarios.

Negative tests are important because reliable autonomous systems are defined as much by how they fail as by how they succeed.

---

## 17. Do Not Overfit to One Successful Prompt

A feature that succeeds for one exact natural-language prompt is not necessarily robust.

Where practical, test variations involving:

* Explicit paths.
* Node names.
* Nested nodes.
* Missing nodes.
* Missing parents.
* Ambiguous names.
* Already-existing state.
* Repeated requests.
* Multi-step recovery.

Distinguish between:

* A tool working.
* A model successfully choosing the tool.
* The complete agent reliably handling the user intent.

These are separate forms of verification.

---

## 18. Maintain Clear Sources of Truth

Static documentation and dynamic project state must remain separate.

Stable architectural and behavioral rules belong in stable documents.

Frequently changing information belongs in dynamic project documents.

Do not duplicate changing implementation status across multiple files.

The primary dynamic documents are responsible for:

* Current implementation state.
* Test history.
* Roadmap progress.
* Tool protocol details.

Before changing a dynamic document, ensure that it is the correct source of truth for that information.

---

## 19. Update Documentation After Meaningful Changes

After a feature is implemented and verified, update the appropriate dynamic documentation.

Examples:

* Current working behavior belongs in `docs/CURRENT_STATE.md`.
* Verified tests and discovered regressions belong in `docs/TEST_HISTORY.md`.
* Future development priorities belong in `docs/ROADMAP.md`.
* Tool request and response semantics belong in `docs/TOOL_PROTOCOL.md`.

Do not update static rule or architecture documents merely because ordinary implementation progress changed.

---

## 20. The Long-Term Goal Must Guide Architectural Decisions

The immediate objective is not merely to create isolated Godot editor commands.

The project is moving toward an AI-powered Godot Editor agent capable of understanding development intent and performing increasingly sophisticated editor-native work.

Long-term capabilities may eventually include:

* Scene inspection and modification.
* Node and hierarchy management.
* Property editing.
* Script-related operations.
* Resource operations.
* Multi-step planning.
* Iterative verification.
* Error recovery.
* Provider routing.
* Human oversight.
* Permission boundaries.
* Undoable operations.
* Detailed operation logs.

The architecture should remain capable of growing toward this goal.

However, future ambitions must not justify implementing unnecessary complexity before the underlying foundations are reliable.

Build the foundation first.

---

## 21. Preserve Human Control

The long-term system should assist developers rather than silently take ownership of their projects.

As the agent becomes more capable, the architecture should support:

* Observable actions.
* Clear operation history.
* Undoable modifications where possible.
* Future confirmation mechanisms.
* Future permission boundaries.
* Explicit handling of destructive operations.

Do not design the system around hidden autonomous changes.

Developer trust is a functional requirement.

---

## 22. Prefer Correctness Over Artificial Step Efficiency

Do not optimize away necessary reasoning or verification merely to reduce the number of model calls.

A multi-step sequence that:

1. Inspects the scene.
2. Finds the correct node.
3. Performs the operation.
4. Verifies the result.

may be preferable to a shorter sequence based on assumptions.

At the same time, avoid wasteful repeated actions when deterministic information is already available.

The goal is efficient correctness, not minimum step count.

---

## 23. Avoid Infinite Recovery Loops

Iterative reasoning must have bounded execution.

Recovery attempts should use new information or a materially different strategy.

Do not allow repeated retries of equivalent failing actions without state changes.

The agent must eventually:

* Complete the task.
* Report an unrecoverable failure.
* Or stop because its execution budget has been reached.

The stopping behavior should be observable and understandable.

---

## 24. Treat User Intent as More Important Than Model Convenience

The system exists to satisfy the user's request safely and correctly.

Do not distort user intent merely because:

* A model omitted a field.
* A tool prefers a simpler path.
* A provider returned incomplete output.
* A previous observation is easier to reuse than current state.

Deterministic repair may fill in information only when the intended value is clear.

When intent is ambiguous, do not invent operations.

---

## 25. Final Rule

When uncertain, prefer:

**Understand → Observe → Validate → Modify → Verify → Record**

over:

**Assume → Execute → Hope**

The second approach has already powered enough software development decisions on this planet.

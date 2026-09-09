# Provider Contract V1

## Scope and status

This document records the provider contract implemented by the current source as of 2026-09-05. Gemini is the primary provider and Groq is the active parity target. OpenRouter, Ollama, and Z.ai implement compatible entry points (five adapters total) but are not active parity targets for this phase.

The contract is the behavior required at the boundary of `agent/godot_agent.py`; it is not a redesign proposal.

## 1. Agent-facing provider contract

The agent-facing callable is the provider branch behind `ask_model(conversation)`:

```text
ask_model(conversation: list[dict[str, str]]) -> str
```

The provider must:

- accept the complete current conversation as dictionaries with `role` and `content`;
- accept the JSON schema generated from the Pydantic `AgentDecision` discriminated union;
- perform provider-specific request construction internally;
- return the model response as a raw JSON string, not a provider SDK object and not a parsed decision. Internally each adapter wraps that text with normalized usage metadata in a `agent/telemetry.ProviderResult(text, usage)` envelope; the agent-facing `ask_model()` still returns only the text string;
- raise an exception when the request cannot produce a usable response; the agent catches provider-call failures and ends the session gracefully;
- return a JSON object representing exactly one next `AgentDecision`, or return malformed/missing data that the agent will reject rather than silently accept.

### Usage metadata

All four adapters (Gemini, Groq, OpenRouter, Ollama) return
`ProviderResult`, which carries the response text plus a normalized
`TokenUsage`. `normalize_usage()` maps provider-specific usage fields
to `input_tokens` / `output_tokens` / `total_tokens`:

- Gemini: `prompt_token_count`, `candidates_token_count`, `total_token_count`
- OpenAI-compatible: `prompt_tokens`, `completion_tokens`, `total_tokens`
- Ollama: `eval_count`

When a provider exposes no usage metadata, the fields remain `None`
with `available=False`; values are never estimated or fabricated.
The agent records this usage in model-call telemetry, and failed
calls are recorded with a duration and a `safe_error_message()` that
truncates the text to 200 characters and redacts `GEMINI_API_KEY`,
`GROQ_API_KEY`, `OPENROUTER_API_KEY`, and `ZAI_API_KEY` values.

The provider does not execute tools, validate Godot paths, enforce batch boundaries, compact context, or perform final-answer handling. Those responsibilities remain in Python orchestration and the Godot bridge.

### Canonical conversation messages

The agent creates these roles:

- `system`: the complete agent instruction prompt;
- `user`: the original request and subsequent execution-result or batch-boundary instructions;
- `assistant`: the previously accepted decision serialized with Pydantic;
- `tool`: a JSON-serialized result from Python/Godot execution.

The provider may translate these messages for its API, but must preserve their meaning and ordering. The internal `tool` role is not native model tool calling.

### Response processing after the provider returns

The agent applies the same provider-independent pipeline:

1. normalize only the known nested `parameters` envelope;
2. reject invalid JSON or unsafe normalization;
3. validate the result with the Pydantic `AgentDecision` adapter;
4. apply deterministic request constraints;
5. validate action-specific required fields and `set_properties` JSON;
6. reject unknown actions and blocked resumed batch mutations;
7. execute one action or a bounded batch;
8. append the decision and result, compact older execution results, and call the provider again;
9. stop on `final_answer`, provider/validation failure, or the maximum step limit.

`AgentDecision` is a discriminated union of the supported inspection, mutation, prototype, `batch`, and `final_answer` actions. Batches contain 1 to `MAX_BATCH_SIZE` validated non-final actions. The current maximum is 5.

## 2. Gemini implementation

`models/gemini_provider.py` currently:

- lazily reads `GEMINI_API_KEY` and creates a `google.genai.Client` on the first call;
- accepts `conversation` and the generated schema;
- concatenates all system messages into `system_instruction`;
- flattens user, assistant, and tool messages into one text prompt using `USER:`, `ASSISTANT:`, and `TOOL RESULT:` labels;
- converts Pydantic `oneOf` to `anyOf` recursively and removes the provider-incompatible constraint keywords `discriminator`, `minimum`, `maximum`, `minItems`, and `maxItems`, because the Gemini response-schema surface does not accept them;
- requests `application/json` with the converted `response_schema` through `client.models.generate_content`;
- retries only `google.genai.errors.ServerError` up to three total attempts, with 1 and 2 second backoffs;
- does not retry missing-key, client/request, schema, empty-response, or other non-server errors;
- raises the provider/SDK exception for request failures and raises `RuntimeError` for empty text;
- returns `ProviderResult(text=response.text, usage=normalize_usage(response.usage_metadata))` to the agent.

Gemini therefore provides the stronger remote structured-output constraint of the two active adapters, while local Pydantic validation remains authoritative.

## 3. Groq implementation

`models/groq_provider.py` currently:

- reads `GROQ_API_KEY` on every call and raises `RuntimeError` when it is absent;
- uses the fixed model `openai/gpt-oss-120b`;
- copies each conversation message and translates internal `tool` messages to `user` messages beginning with `AGENT EXECUTION RESULT:` plus a note that the result is not native tool calling; it removes `tool_call_id` and `tool_calls` if present;
- preserves system, user, and assistant messages as chat messages;
- requests `response_format={"type": "json_object"}` and `reasoning_effort="medium"`, but does not send the Pydantic schema to Groq;
- constructs a `Groq` client with `max_retries=4`, relying on SDK retry behavior for transient/API failures and 429 handling;
- reads `x-ratelimit-*` headers through `with_raw_response` when supported, caches remaining request/token budget, and proactively sleeps up to 30 seconds when headroom is low;
- falls back to a normal completion call if the installed SDK lacks `with_raw_response`, losing header visibility and proactive pacing;
- logs recognized rate-limit/API-status failures and re-raises all request exceptions;
- raises `RuntimeError` for an empty or missing message content;
- returns `ProviderResult(text=response.choices[0].message.content, usage=normalize_usage(response.usage))` to the agent.

Groq's response is consequently subject to local Pydantic validation but only JSON-object constrained remotely, not schema constrained remotely.

## 4. Differences and parity risks

| Difference | Classification | Finding |
|---|---|---|
| Gemini flattens conversation into one labeled prompt; Groq sends chat messages | implementation detail | Both adapters receive and preserve the same internal message sequence, but the model-facing representation differs because the SDKs use different request surfaces. |
| Gemini sends system instructions separately; Groq preserves a system chat message | implementation detail | This is provider API mapping, provided system semantics remain intact. |
| Gemini converts and sends the Pydantic schema; Groq sends JSON-object mode only | behavioral difference | Groq can return structurally valid JSON that is not an `AgentDecision`; local validation rejects it. It may also produce more missing/invalid fields before validation. |
| Gemini labels tool results as `TOOL RESULT`; Groq rewrites them as user messages with `AGENT EXECUTION RESULT` | behavioral difference | Continuation interpretation can differ because tool results have different role and wording at the model boundary. |
| Neither adapter uses native function/tool calling | implementation detail | Python executes all actions and supplies results as conversation context. |
| Gemini retries only server errors, three total attempts, fixed 1/2 second backoff | behavioral difference | Transient recovery timing and recoverable error classes differ from Groq. |
| Groq uses SDK retries up to four retries and proactive rate-limit pacing | behavioral difference | Groq may wait longer before returning and can behave differently near quota windows. |
| Groq's header pacing disappears on older SDKs | parity risk | The same code can have different latency and 429 behavior depending on installed Groq SDK capability. |
| Gemini client initialization is cached after first call; Groq client is constructed per call | implementation detail | This changes setup overhead and client lifecycle, but not the intended raw-string contract. |
| Missing credentials use different exception types/messages | implementation detail | The agent treats both as provider-call failures; callers should not depend on exact exception classes. |
| Empty responses are rejected by both adapters | implementation detail | The exception type/message differs, while the agent-facing outcome is failure. |
| Both providers rely on provider output to choose one next decision | parity risk | Different prompt/message mappings and remote constraints can change action selection, omission rates, or final-answer timing even when the agent contract is identical. |
| Context compaction happens before the next provider call | implementation detail | Both providers receive the same mutated conversation from Python, but their different message mappings may amplify interpretation differences in compacted summaries. |
| Batch-boundary enforcement occurs before execution in Python | implementation detail/invariant | Provider behavior cannot bypass the hard block; a provider may propose a blocked action, but Godot is not called. |

### Current parity conclusion

Gemini and Groq satisfy the same narrow callable contract: conversation plus schema in, raw response text out or exception. They do not currently provide equivalent remote structured-output guarantees or equivalent model-facing conversation semantics. Gemini-Groq parity must therefore not be declared based only on successful API calls; deterministic contract tests and representative live tasks are required.

No provider behavior is changed by this audit.

## 5. Deterministic parity test matrix

These tests should run against both adapters with SDK/client calls mocked. They must assert the normalized agent-facing result and the request mapping separately. They must not require API keys, network access, Godot, or a live model.

| Case | Deterministic assertion |
|---|---|
| Valid structured action | Provider returns raw JSON that parses into a valid action; request receives the complete conversation and schema input. |
| Valid final response | Provider returns a valid `final_answer`; the agent terminates without a tool call. |
| Malformed JSON | Raw invalid JSON reaches the common normalization/validation path and is rejected with no Godot execution. |
| Missing required fields | Missing action-specific fields are rejected by Pydantic or deterministic action validation. |
| Invalid action/tool name | Unknown discriminator/action is rejected; no tool dispatch occurs. |
| Invalid tool arguments | Invalid `set_properties` JSON or missing path arguments yields a structured validation result and continuation request. |
| Tool-result continuation | A prior assistant decision and tool result are represented in the provider request; the next valid decision is accepted. |
| Multi-step tool loop | Mocked provider responses drive multiple actions, results, and a final answer in order. |
| Provider error | Provider exception is caught at the agent boundary, logged, and does not call Godot afterward. |
| Retry behavior | Gemini retries only mocked `ServerError`; Groq honors mocked SDK retry configuration and re-raises after exhaustion. |
| Context compaction | Older large execution results become summaries while the two most recent execution results remain full before either provider is called. |
| Batch-boundary enforcement | A provider response matching a skipped mutation, including a same-target parameter change, is rejected before tool execution; read-only recovery remains allowed. |

The adapter-level half should inspect Gemini's `response_schema` conversion and Groq's `response_format`/message conversion. The contract-level half should exercise the shared agent functions with provider responses mocked. Keep these distinct from live API tests.

## 6. Live E2E scenarios

Run each scenario separately with the same agent-level request and a clean disposable Godot scene, first with Gemini and then with Groq:

1. **Inspection:** "Find every node named `PersistentEnemy` and report the exact scene-relative paths." This tests discovery, tool-result continuation, and final answer accuracy without mutation.
2. **Verified creation:** "Create a `Node2D` named `ParityProbe` under the scene root, verify it exists, then report its path." This tests an undoable mutation, ownership, post-operation verification, and final response.
3. **Recovery:** "Rename `PersistentEnemy` to `ParityEnemy`, using discovery first if needed, then verify the resulting path." This tests path resolution, mutation result interpretation, and multi-step continuation.
4. **Interrupted batch boundary:** Use a controlled request that causes a batch with a deliberately invalid middle action and a skipped final mutation, then verify that neither Gemini nor Groq can resume the skipped target automatically. This validates the Python invariant rather than model wording.

Record provider, model, SDK versions, request outcome, step count, retries, tool results, and final answer. Do not compare exact wording as a parity criterion; compare action correctness, safety, and verified editor state.

## Recommended next task

Implement the deterministic provider-contract test harness for the shared agent normalization/validation path and isolated Gemini/Groq request mapping. Do not add fallback routing or change provider behavior as part of that work.

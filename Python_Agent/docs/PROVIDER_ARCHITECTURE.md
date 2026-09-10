# PROVIDER_ARCHITECTURE.md

## Purpose

This document defines the intended architecture for AI model providers used by the Godot AI Agent.

The project must support multiple language-model providers without coupling the core agent loop to one specific provider.

The provider architecture exists to allow the agent to use different models for different workloads while preserving a single structured reasoning and tool-execution pipeline.

The currently relevant providers are:

- Gemini.
- Groq.
- Ollama.
- OpenRouter.
- Z.ai.

Future providers may be added when they provide a practical benefit.

A Poolside (Laguna) adapter was evaluated in September 2026 and
removed: structured-output compliance with the real agent prompt
was good, but the model could not reliably conclude an agent turn
after tool results (it re-searched or answered in prose instead of
emitting `final_answer`), making it unfit for the turn-based loop.
Revisit only if Poolside's chat behavior changes materially.

The core agent must not depend on provider-specific implementation details.

---

# 1. Architectural Goal

The desired architecture is:

    User Request
        |
        v
    Core Agent
        |
        v
    Provider Selection
        |
        v
    Provider Adapter
        |
        v
    AI Model
        |
        v
    Structured Agent Decision
        |
        v
    Decision Validation
        |
        v
    Godot Tool Execution
        |
        v
    Structured Observation
        |
        v
    Core Agent

The core agent should reason in terms of:

- user requests,
- conversation context,
- structured decisions,
- tool results,
- failures,
- recovery,
- completion.

It should not need to know:

- Gemini SDK request objects,
- Groq SDK request objects,
- Ollama HTTP details,
- provider-specific response object structures.

Those details belong inside provider adapters.

---

# 2. Provider Independence

The core agent should interact with providers through a common interface.

Conceptually:

    provider.generate_decision(
        messages=...,
        system_context=...,
        decision_schema=...
    )

The exact implementation may differ, but the core principle is:

The provider returns a normalized result that the agent can process independently of which model produced it.

The agent must not contain large blocks such as:

    if provider == "gemini":
        ...

    elif provider == "groq":
        ...

    elif provider == "ollama":
        ...

inside the reasoning loop.

Provider-specific branching should remain inside the provider layer or provider factory.

---

# 3. Normalized Provider Responsibilities

Every provider adapter should be responsible for:

1. Receiving the agent's normalized request.
2. Constructing the provider-specific model request.
3. Supplying the appropriate system instructions.
4. Supplying the current conversation and tool context.
5. Requesting structured output where the provider supports it.
6. Receiving the raw model response.
7. Extracting the model's structured decision.
8. Normalizing provider-specific errors.
9. Returning a common result to the core agent.

The core agent should receive the same general result shape regardless of provider.

---

# 4. Normalized Provider Result

The exact implementation may evolve, but conceptually a provider call should return information similar to:

    {
        "success": true,
        "provider": "gemini",
        "model": "model-name",
        "raw_response": "...",
        "decision_data": {
            ...
        }
    }

When a provider request fails:

    {
        "success": false,
        "provider": "groq",
        "model": "model-name",
        "error": "Provider request failed"
    }

The core agent should not need to parse provider SDK exceptions directly.

Provider adapters should convert provider-specific failures into useful normalized failures.

---

# 5. Gemini

Gemini is currently the primary cloud reasoning provider.

Gemini is useful for:

- fast cloud inference,
- structured reasoning,
- tool-oriented planning,
- general agent development.

The existing implementation may currently contain Gemini-specific logic directly inside the agent.

Future provider abstraction should extract this logic rather than rewriting working behavior unnecessarily.

The first abstraction step should preserve current Gemini functionality.

Do not break the existing working agent while introducing provider abstraction.

A successful migration means:

1. Existing Gemini behavior continues to work.
2. The core agent no longer directly depends on Gemini SDK details.
3. Another provider can be added through the same interface.

---

# 6. Groq

Groq is intended as an additional cloud inference provider.

The current candidate models should be treated as configurable rather than hard-coded into the core agent.

Relevant model categories include:

- larger reasoning-capable models,
- smaller fast models,
- specialized safety models,
- speech models where future functionality may require them.

For the Godot AI Agent, the most relevant initial use case is language-model reasoning and structured decision generation.

The provider integration should make model selection configurable.

Conceptually:

    GROQ_MODEL = environment or configuration value

The provider architecture should not require source-code modification merely to test another Groq model.

---

# 7. Ollama

Ollama provides local inference.

It is useful for:

- offline development,
- local experimentation,
- privacy-sensitive workflows,
- testing without cloud API costs,
- fallback when cloud providers are unavailable.

Ollama should use the same normalized provider interface as cloud providers.

The core agent should not need a separate reasoning loop for Ollama.

The provider adapter should handle:

- local endpoint communication,
- model selection,
- request formatting,
- response parsing,
- structured-output extraction.

---

# 8. Provider Selection

Provider selection should eventually be explicit and configurable.

Possible mechanisms include:

- environment variables,
- configuration files,
- command-line arguments,
- editor settings,
- runtime provider selection.

The initial implementation should favor the simplest mechanism that does not require editing source code.

Conceptually:

    GODOT_AI_PROVIDER=gemini

or:

    GODOT_AI_PROVIDER=groq

or:

    GODOT_AI_PROVIDER=ollama

Model selection should be independently configurable.

Conceptually:

    GODOT_AI_MODEL=...

The provider and model should be treated as separate configuration concepts.

---

# 9. Fallback Strategy

Fallback behavior should not be introduced prematurely.

The first milestone is reliable explicit provider selection.

Automatic fallback introduces additional complexity:

- repeated requests,
- cost control,
- duplicated operations,
- inconsistent responses,
- hidden provider switching.

Once provider abstraction is stable, fallback may be added deliberately.

A possible future strategy is:

    Primary Provider
        |
        | request failure
        v
    Retry Policy
        |
        | unrecoverable provider failure
        v
    Optional Fallback Provider

Fallback must not automatically repeat Godot mutation tools.

Provider fallback applies to model reasoning requests.

Godot operations remain governed by their own structured tool results and safety rules.

---

# 10. Structured Output

The agent relies on structured decisions.

Provider adapters should attempt to obtain structured JSON output through the best mechanism supported by each provider.

Possible provider capabilities include:

- JSON mode,
- schema-constrained output,
- function calling,
- tool calling,
- prompted JSON output.

The core agent should receive normalized decision data.

Provider-specific structured-output mechanisms must remain inside the adapter.

The architecture must tolerate providers with weaker structured-output guarantees.

For such providers, the adapter may need to:

1. receive raw text,
2. extract candidate JSON,
3. validate the structure,
4. return a normalized parsing failure if extraction fails.

Do not allow unvalidated raw model text to directly control Godot editor operations.

All decisions must pass through the existing decision validation layer.

---

# 11. Conversation and Iterative Reasoning

The provider must receive sufficient context for multi-step reasoning.

At each agent step, relevant information may include:

- the original user request,
- prior agent decisions,
- previous tool results,
- current recovery context,
- system instructions,
- decision schema requirements.

The core agent owns the reasoning state.

The provider should not become the permanent source of truth for agent state.

This is important because:

- providers may change,
- models may be swapped,
- requests may fail,
- conversation formats differ between providers.

The agent's state should remain provider-independent.

---

# 12. Raw Response Logging

Raw model responses are useful during development.

They help diagnose:

- malformed JSON,
- omitted required fields,
- incorrect action selection,
- provider-specific formatting behavior,
- structured-output failures.

Raw responses should be observable in development logs.

However, the operational pipeline must use validated structured decisions rather than trusting raw text.

The distinction is:

    Raw response
        |
        v
    Parsing
        |
        v
    Validation
        |
        v
    Agent decision
        |
        v
    Constraint repair where safe
        |
        v
    Tool dispatch

---

# 13. Provider Error Handling

Provider errors should be distinguishable from tool errors.

Examples of provider failures:

- invalid API key,
- authentication failure,
- network failure,
- rate limit,
- model unavailable,
- malformed provider response,
- structured-output parsing failure.

Examples of Godot tool failures:

- node not found,
- parent not found,
- invalid node path,
- missing required operation field.

These are different failure domains.

The core agent should not attempt to solve:

    invalid API key

by searching the Godot scene tree.

Humans have somehow required this distinction to be explicitly documented, so here it is.

Provider failures should normally terminate or retry the model request according to provider-level policy.

Tool failures should normally be presented to the model as observations for iterative recovery.

---

# 14. Retry Policy

Provider retries should be conservative.

Retries may be appropriate for:

- temporary network failures,
- transient server errors,
- temporary rate limits when a delay is acceptable.

Retries should not blindly repeat requests indefinitely.

The retry policy should eventually consider:

- maximum retry count,
- exponential or bounded backoff,
- error classification,
- provider rate limits,
- cost implications.

Initial implementation should remain simple and observable.

Do not add complex automatic retry behavior without logging.

---

# 15. Configuration and Secrets

API keys and provider credentials must not be hard-coded into source files.

Credentials should be loaded from an appropriate local configuration mechanism such as:

- environment variables,
- local ignored configuration files,
- secure credential storage where available.

Files containing secrets must not be committed to version control.

The repository may contain an example configuration file documenting required variable names without containing real credentials.

Example concepts:

    GEMINI_API_KEY
    GROQ_API_KEY
    OLLAMA_BASE_URL

The exact variable names should be confirmed by the implementation.

---

# 16. Recommended Initial Provider Interface

The first abstraction should remain small.

A conceptual interface may contain operations equivalent to:

    generate_decision(...)

The interface should not attempt to anticipate every future capability.

Avoid designing a giant universal AI SDK abstraction before the project actually needs one.

The initial goal is simply:

    User request and agent state
        |
        v
    Provider adapter
        |
        v
    Structured model response
        |
        v
    Validated agent decision

Additional capabilities such as streaming, embeddings, image input, audio, or autonomous tool calling should be added when the project has a concrete need for them.

---

# 17. Provider Factory

Provider creation should eventually be centralized.

Conceptually:

    create_provider(provider_name, configuration)

The factory determines which adapter to instantiate.

Examples:

    GeminiProvider

    GroqProvider

    OllamaProvider

The core agent should receive a provider object rather than constructing provider SDK clients directly.

This improves:

- testability,
- provider switching,
- configuration management,
- future expansion.

---

# 18. Testing Provider Integrations

Each provider should be tested independently.

Minimum provider tests should include:

1. Provider initializes successfully.
2. Authentication or endpoint configuration is validated.
3. A simple reasoning request succeeds.
4. A structured decision is returned.
5. Malformed output is handled safely.
6. Provider failures are distinguishable from tool failures.

After provider-level testing, test the provider through the full agent loop.

Example end-to-end test:

    User request
        |
        v
    Provider generates find_nodes decision
        |
        v
    Godot tool executes
        |
        v
    Tool result returned
        |
        v
    Provider generates next decision
        |
        v
    Task completes

Do not consider a provider fully integrated merely because one API request returns text.

---

# 19. Long-Term Provider Roles

The long-term system may use different providers for different tasks.

Possible roles include:

- primary reasoning model,
- fast planning model,
- local/offline model,
- fallback model,
- code-specialized model,
- safety or validation model.

However, role-based routing should be introduced only when measurable benefits justify the additional complexity.

The immediate objective is provider interchangeability.

First make:

    Gemini

work through the abstraction.

Then add:

    Groq

Then verify:

    Ollama

Only after all providers share the same stable contract should intelligent routing be considered.

---

# 20. Non-Goals for the Initial Abstraction

The initial provider abstraction does not need to solve:

- autonomous multi-model debates,
- dynamic model auctions,
- automatic cost optimization,
- provider benchmarking during every request,
- hidden provider switching,
- complex fallback graphs,
- distributed inference.

The project should first establish a reliable provider boundary.

Simple and testable architecture is more valuable than an impressive diagram that collapses the first time a network request fails.

---

# 21. Ultimate Architectural Role

The provider layer is only one component of the larger Godot AI Agent.

The ultimate system architecture is:

    User
        |
        v
    Godot AI Assistant Interface
        |
        v
    Agent Orchestration
        |
        +--------------------+
        |                    |
        v                    v
    Provider Layer       Agent State
        |                    |
        v                    |
    AI Models               |
                             |
        +--------------------+
        |
        v
    Structured Decisions
        |
        v
    Validation and Safety Layer
        |
        v
    Godot Tool Bridge
        |
        v
    Godot EditorPlugin
        |
        v
    Godot Project and Editor

The provider layer must remain replaceable.

The Godot operations and core reasoning architecture must survive changes in model vendors.

---

# 22. Implementation Priority

The recommended implementation order is:

1. Identify Gemini-specific code currently inside the agent.
2. Define a minimal provider interface.
3. Move Gemini behavior behind that interface without changing working behavior.
4. Verify all existing agent tests still pass.
5. Add the Groq provider.
6. Test Groq independently.
7. Test Groq through the full iterative agent loop.
8. Add or migrate Ollama behind the same interface.
9. Verify provider selection.
10. Only then consider fallback or routing.

The guiding rule is:

    Preserve working behavior first.
    Abstract second.
    Expand providers third.
    Optimize later.

---

# 23. Documentation Maintenance

Update this document when:

- a provider is added,
- the provider interface changes,
- configuration semantics change,
- structured-output handling changes,
- retry or fallback behavior changes,
- provider roles become part of the architecture.

Dynamic information such as:

- currently tested models,
- active provider configuration,
- temporary provider issues,
- latest successful tests,

belongs in:

    docs/CURRENT_STATE.md

or:

    docs/TEST_HISTORY.md

This document should describe stable architectural intent rather than temporary runtime state.
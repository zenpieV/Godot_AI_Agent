# MODEL_KNOWLEDGE_DRIFT.md

## Purpose

This document records a known, bounded weakness of the agent: the
reasoning models available through the provider abstraction have no
web access and fixed training cutoffs. It analyzes where that
matters in this architecture, where it does not, and records the
agreed fix direction. It complements `FUTURE_TOOLS.md`, where the
proposed fix tools are tracked as a batch proposal.

Written 2026-09-10, after the script tools milestone made the
concrete drift risk acute (see below).

---

# The concern

The reasoning models (Gemini flash variants, Groq, local Ollama
models) cannot search the web. Their knowledge of Godot — its API,
idioms, and community practices — is frozen at their training
cutoffs. Two failure modes follow:

1. The model may not know APIs, renames, or removals introduced in
   engine versions newer than its cutoff (this project runs Godot
   4.7.2).
2. The model has no visibility into current community practice,
   tooling, or ecosystem trends.

The naive conclusion — "the agent is outdated" — is wrong for this
architecture, but the concern is real in specific places.

---

# Where the agent is drift-resistant (by design)

The architecture's core decision — **the running editor is the
authority, never the model's memory** — makes tool-mediated
operations structurally safe against model staleness:

- `list_available_node_types` / `get_node_class_info` /
  `validate_node_type` read the real ClassDB of the running
  editor. The model cannot create a node type that does not exist
  in 4.7.2, no matter what it believes.
- `get_node_properties` / `get_node_property` read real property
  state with real types.
- The signal tools validate `has_signal` / `has_method` before
  acting and read connections back from live state.
- `list_script_diagnostics` parse-checks against the actual engine
  parser, not the model's memory of GDScript.
- Godot-side validation refuses invented names, paths, and
  identifiers with structured errors, feeding the model's recovery
  loop with ground truth.

For everything the agent *does through tools*, model staleness
degrades gracefully into "the model needs a recovery loop" — which
the agent loop is designed for. This was a deliberate design
principle (ROADMAP Phase 3: "The Python agent should not invent
Godot property schemas. Godot should remain the authoritative
environment for validating actual node types and properties.") and
it is what makes fixed model cutoffs survivable.

---

# Where drift actually bites

## 1. GDScript generation (the sharp edge)

`create_script` content comes from the model's memory. A
post-cutoff API rename or removal can produce code that parses
cleanly but is functionally wrong. The parse gate catches syntax
errors and some typed-call errors, but unknown method calls on
untyped variables compile fine — and because runtime/playtest
tools do not exist yet, the failure mode today is **silent** until
a human runs the game.

Note the pattern: the drift risk is concentrated in exactly the
newest capability (code generation), not in the long-standing
tool surface.

## 2. Community trends

Best practices, addon ecosystem, idiom shifts: genuinely
unreachable without web access. In practice this is mostly input
the human developer brings to the session, not something the
agent discovers.

---

# Fix options (evaluated)

## Option A — Version-matched offline documentation tools (recommended)

Bundle the official Godot class-reference XML (shipped per engine
release) with the Python agent and expose two read-only tools:

- `get_class_documentation(class_name)` — bounded, structured
  class reference: description, methods, properties, signals,
  enums, with per-member descriptions.
- `search_documentation(query)` — bounded search across class and
  member names/descriptions.

Why this is the right fix for this project:

- **Exact version match**: the docs match the running editor's
  engine version (4.7.2) — better than the model's memory AND
  better than a live web fetch, which returns latest-release docs
  that may not match the editor.
- **Offline-friendly**: works for local-model (Ollama) workflows;
  no network dependency.
- **Deterministic and curated**: no prompt-injection surface from
  open-web content entering a conversation that holds editor
  mutation rights.
- **Fits the architecture**: structured data over text parsing;
  read-only; batchable; provider-independent.

Technical note: the editor's own built-in docs are accessible in
C++ via `EditorHelp::get_doc_data()`, but that API is not exposed
to GDScript plugins (see godot-proposals #12531 and #13608). If a
future Godot release exposes it, reading the editor's live DocData
directly becomes the preferred source; until then, bundling the
per-release docs XML (version-pinned to the engine the project
targets) is the practical path.

## Option B — Bounded `fetch_url` tool (deferred)

Covers community trends and arbitrary pages. Caveats that keep it
deferred:

- Web content becomes tool results in the conversation — an
  untrusted-instruction injection surface in a system with editor
  mutation rights.
- Network/SSRF surface on the bridge side.
- Non-deterministic, unbounded content.

If built, v1 should be restricted to **user-provided URLs only**
("fetch this page I am looking at"), never open-ended search, and
content should be size-bounded and clearly attributed as external
input in the conversation.

## Option C — Ride model upgrades (free, partial)

The provider abstraction makes newer models with newer training
data a configuration change. This is the zero-cost partial fix and
should be exercised opportunistically. Provider-specific built-in
search features are deliberately avoided: they conflict with the
project's provider-independence principle and behave differently
across providers.

---

# Decision

- Option A is tracked as a proposed batch in `FUTURE_TOOLS.md`
  (Tier 2 — documentation and knowledge tools). It directly
  hardens the code-generation capability introduced by the script
  tools.
- Option B is deferred until a concrete need appears, with the
  user-provided-URL restriction as a design precondition.
- Option C is practiced opportunistically via
  `config/settings.py`.
- Runtime feedback (playtest tools, `FUTURE_TOOLS.md` Tier 3)
  remains the other half of the long-term answer for code
  correctness: parsing proves the code compiles, only running it
  proves it works.

from models.ollama_provider import ask_ollama
from models.gemini_provider import ask_gemini
from models.groq_provider import ask_groq
from models.openrouter_provider import ask_openrouter
from models.zai_provider import ask_zai

from config.settings import (
    MODEL_PROVIDER,
    MAX_BATCH_SIZE,
    GEMINI_MODEL,
    OLLAMA_MODEL,
    OPENROUTER_MODEL,
    ZAI_MODEL,
)
from models.groq_provider import GROQ_MODEL

import json
import os
import re
import logging
import uuid
import time

from pydantic import (
    TypeAdapter,
    ValidationError,
)

from typing import Optional

from agent.schemas import AgentDecision
from agent.telemetry import (
    ProviderResult,
    SessionObservability,
    TokenUsage,
    export_session_jsonl,
    safe_error_message,
)

from agent.registry import ACTION_REGISTRY
from agent.mutation import (
    build_mutation_record,
    is_mutation_action,
    classify_verification,
    extract_mutation_target,
)


# ==========================================
# Structured decision adapter
# ==========================================

AGENT_DECISION_ADAPTER = TypeAdapter(
    AgentDecision
)


# ==========================================
# Logging
# ==========================================

class SessionIdFilter(logging.Filter):

    def __init__(
        self,
        session_id: str,
    ):
        super().__init__()
        self.session_id = session_id

    def filter(
        self,
        record,
    ) -> bool:

        if not hasattr(
            record,
            "session_id",
        ):
            record.session_id = (
                self.session_id
            )

        return True


# ==========================================
# 1. Action requirements
# ==========================================
#
# Required fields per action now live in agent/registry.py
# (ActionSpec.required_fields), which is the single source of
# truth shared by validation and dispatch. See
# tests/test_registry.py for the consistency guarantees.


from agent.boundary import (
    compute_action_fingerprint,
    extract_mutation_target,
    is_action_blocked,
    check_decision_blocked,
)


def get_missing_required_fields(
    decision: AgentDecision,
) -> list[str]:

    required_fields = (
        ACTION_REGISTRY[
            decision.action
        ].required_fields
        if decision.action
        in ACTION_REGISTRY
        else None
    )

    if required_fields is None:
        return []

    missing_fields = []

    for field_name in required_fields:

        value = getattr(
            decision,
            field_name,
            None,
        )

        if isinstance(
            value,
            str,
        ):

            if not value.strip():

                missing_fields.append(
                    field_name
                )

        elif value is None:

            missing_fields.append(
                field_name
            )

    return missing_fields


def validate_agent_action(
    decision: AgentDecision,
) -> tuple[bool, str]:

    if (
        decision.action
        not in ACTION_REGISTRY
    ):

        return (
            False,
            (
                "Unknown agent action: "
                + str(
                    decision.action
                )
            ),
        )

    missing_fields = (
        get_missing_required_fields(
            decision
        )
    )

    if missing_fields:

        return (
            False,
            (
                str(
                    decision.action
                )
                + " requires non-empty field(s): "
                + ", ".join(
                    missing_fields
                )
                + "."
            ),
        )

    if (
        decision.action
        == "set_properties"
    ):

        try:

            parsed_properties = (
                json.loads(
                    decision.properties_json
                )
            )

        except (
            TypeError,
            json.JSONDecodeError,
        ):

            return (
                False,
                (
                    "set_properties requires "
                    "properties_json to contain "
                    "valid serialized JSON."
                ),
            )

        if not isinstance(
            parsed_properties,
            dict,
        ):

            return (
                False,
                (
                    "set_properties requires "
                    "properties_json to encode "
                    "a JSON object."
                ),
            )

    return (
        True,
        "",
    )


# ==========================================
# 2. Deterministic request constraint helpers
# ==========================================

def extract_parent_path_from_request(
    request: str,
) -> Optional[str]:

    normalized_request = (
        request.strip()
    )

    patterns = [

        r"\bunder\s+([A-Za-z_][A-Za-z0-9_/]*)",

        r"\binside\s+([A-Za-z_][A-Za-z0-9_/]*)",

        r"\bwithin\s+([A-Za-z_][A-Za-z0-9_/]*)",

        r"\bchildren\s+of\s+([A-Za-z_][A-Za-z0-9_/]*)",

        r"\bdescendants\s+of\s+([A-Za-z_][A-Za-z0-9_/]*)",

    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            normalized_request,
            flags=re.IGNORECASE,
        )

        if match:

            return (
                match.group(1)
            )

    return None


def is_parent_scope_search_request(
    request: str,
) -> bool:

    normalized_request = (
        request.strip()
    )

    search_prefix = (
        r"^(find|search(?:\s+for)?|list|show|get)"
    )

    scope_phrase = (
        r"\b("
        r"under|"
        r"inside|"
        r"within|"
        r"children\s+of|"
        r"descendants\s+of"
        r")\b"
    )

    return bool(

        re.search(
            search_prefix,
            normalized_request,
            flags=re.IGNORECASE,
        )

        and

        re.search(
            scope_phrase,
            normalized_request,
            flags=re.IGNORECASE,
        )

    )


def apply_request_constraints(
    decision: AgentDecision,
    request: str,
) -> AgentDecision:

    if (
        decision.action
        != "find_nodes"
    ):

        return decision

    if decision.parent_path:

        return decision

    inferred_parent_path = (
        extract_parent_path_from_request(
            request
        )
    )

    if not inferred_parent_path:

        return decision

    if not is_parent_scope_search_request(
        request
    ):

        print(
            "\nConstraint repair skipped:"
        )

        print(
            "The parent mentioned in the user "
            "request is part of an operation or "
            "destination, not an automatic "
            "find_nodes search scope."
        )

        return decision

    requested_node_name = (
        decision.node_name
        or ""
    )

    if (
        requested_node_name
        and requested_node_name
        == inferred_parent_path
    ):

        print(
            "\nConstraint repair skipped:"
        )

        print(
            "find_nodes is searching for the "
            "explicit parent node itself, so the "
            "search will remain whole-scene."
        )

        return decision

    print(
        "\nConstraint repair:"
    )

    print(
        "Model omitted parent_path. "
        + "Using explicit parent scope "
        + "from the user request: "
        + inferred_parent_path
    )

    decision.parent_path = (
        inferred_parent_path
    )

    return decision


# ==========================================
# 2.5 Context compaction
# ==========================================

COMPACTION_KEEP_RECENT_STEPS = 2

COMPACTION_SIZE_THRESHOLD_CHARS = 600

COMPACTION_SUMMARY_MAX_PATHS = 25


def flatten_scene_tree_paths(
    node,
    paths=None,
):

    if paths is None:
        paths = []

    if not isinstance(
        node,
        dict,
    ):
        return paths

    path = node.get(
        "path"
    )

    if path:
        paths.append(
            path
        )

    for child in (
        node.get(
            "children",
            [],
        )
        or []
    ):
        flatten_scene_tree_paths(
            child,
            paths,
        )

    return paths


def summarize_tool_result(
    action,
    tool_result,
):

    if not isinstance(
        tool_result,
        dict,
    ):

        return (
            f"{action} result consumed "
            "(non-dict payload omitted)."
        )

    success = tool_result.get(
        "success"
    )

    if (
        action == "get_scene_tree"
        and isinstance(
            tool_result.get(
                "scene_tree"
            ),
            dict,
        )
    ):

        paths = flatten_scene_tree_paths(
            tool_result[
                "scene_tree"
            ]
        )

        total = len(
            paths
        )

        shown = paths[
            :COMPACTION_SUMMARY_MAX_PATHS
        ]

        truncated_note = (
            f" (showing first "
            f"{COMPACTION_SUMMARY_MAX_PATHS} "
            f"of {total})"
            if total
            > COMPACTION_SUMMARY_MAX_PATHS
            else ""
        )

        return (
            "get_scene_tree succeeded. "
            "The full scene tree inspection "
            "was already consumed by the "
            "decision that followed it. "
            f"{total} node(s) total"
            f"{truncated_note}. Paths: "
            + ", ".join(
                shown
            )
        )

    if action == "find_nodes":

        matches = (
            tool_result.get(
                "nodes"
            )
            or tool_result.get(
                "matches"
            )
        )

        if isinstance(
            matches,
            list,
        ):

            total = len(
                matches
            )

            match_paths = [

                (
                    match.get(
                        "path",
                        str(
                            match
                        ),
                    )
                    if isinstance(
                        match,
                        dict,
                    )
                    else str(
                        match
                    )
                )

                for match in matches[
                    :COMPACTION_SUMMARY_MAX_PATHS
                ]

            ]

            truncated_note = (
                f" (showing first "
                f"{COMPACTION_SUMMARY_MAX_PATHS} "
                f"of {total})"
                if total
                > COMPACTION_SUMMARY_MAX_PATHS
                else ""
            )

            return (
                f"find_nodes succeeded. "
                f"{total} match(es) found"
                f"{truncated_note}. Paths: "
                + ", ".join(
                    match_paths
                )
            )

    if (
        action == "get_script_content"
        and isinstance(
            tool_result.get("source"),
            str,
        )
        and tool_result.get("truncated") is True
    ):

        return (
            "get_script_content succeeded. "
            "Paged read of "
            + str(tool_result.get("script_path", "?"))
            + f": lines {tool_result.get('start_line', 1)}"
            + f"-{tool_result.get('end_line', '?')} of "
            + str(tool_result.get("total_lines", "?"))
            + " total. The full read was already "
            "consumed by the decision that "
            "followed it; issue a fresh paged "
            "call for other line ranges."
        )

    if (
        action == "get_node_properties"
        and isinstance(
            tool_result.get("properties"),
            list,
        )
    ):

        props = tool_result["properties"]

        names = [
            str(p.get("name", "?"))
            for p in props[:COMPACTION_SUMMARY_MAX_PATHS]
            if isinstance(p, dict)
        ]

        truncated_note = (
            f" (showing first {COMPACTION_SUMMARY_MAX_PATHS})"
            if len(names) > COMPACTION_SUMMARY_MAX_PATHS
            else ""
        )

        return (
            "get_node_properties succeeded. "
            "Property read of "
            + str(tool_result.get("node_path", "?"))
            + " was already consumed by the "
            "decision that followed it. "
            + str(len(props))
            + " propert(y/ies): "
            + ", ".join(names)
            + truncated_note
            + "."
        )

    serialized = json.dumps(
        tool_result
    )

    if (
        len(
            serialized
        )
        <= COMPACTION_SIZE_THRESHOLD_CHARS
    ):

        return (
            f"{action} result consumed. "
            f"success={success}. "
            + serialized
        )

    message = (
        tool_result.get(
            "message"
        )
        or tool_result.get(
            "error"
        )
        or ""
    )

    return (
        f"{action} result consumed. "
        f"success={success}. "
        f"{message} "
        "[full payload omitted after being "
        f"consumed, ~{len(serialized)} chars]"
    )


def compact_conversation(
    conversation,
    execution_result_records,
    logger,
    observability=None,
    turn_number=0,
    step_number=0,
    ui_reporter=None,
):
    """
    Replace only execution-result messages that are
    older than the fixed recent-history window.

    IMPORTANT:
    The recent-history window is based on position in
    the complete execution-result history, not on the
    subset of records that have not already been
    compacted. This guarantees that the most recent
    COMPACTION_KEEP_RECENT_STEPS execution results
    always remain untouched.
    """

    if (
        len(
            execution_result_records
        )
        <= COMPACTION_KEEP_RECENT_STEPS
    ):
        return

    records_to_consider = (
        execution_result_records[
            :-COMPACTION_KEEP_RECENT_STEPS
        ]
    )

    for record in records_to_consider:

        if record[
            "compacted"
        ]:
            continue

        conversation_index = (
            record[
                "conversation_index"
            ]
        )

        original_content = (
            conversation[
                conversation_index
            ][
                "content"
            ]
        )

        original_length = len(
            original_content
        )

        if (
            original_length
            <= COMPACTION_SIZE_THRESHOLD_CHARS
        ):

            record[
                "compacted"
            ] = True

            continue

        if (
            record[
                "tool_result"
            ]
            is not None
        ):

            summary = (
                summarize_tool_result(
                    record[
                        "action"
                    ],
                    record[
                        "tool_result"
                    ],
                )
            )

        else:

            summary = (
                f"{record['action']} validation "
                "failure was resolved by a later "
                "corrected decision."
            )

        new_content = (
            "AGENT EXECUTION RESULT SUMMARY "
            f"(compacted, step "
            f"{record['step']}):\n"
            + summary
            + "\n\nThis is a compacted summary "
            "of an older result. The original "
            "full payload is no longer available "
            "verbatim. Rely on this summary, or "
            "issue a fresh targeted tool call "
            "(such as find_nodes) if more current "
            "detail is needed."
        )

        conversation[
            conversation_index
        ][
            "content"
        ] = new_content

        record[
            "compacted"
        ] = True

        logger.info(
            "Context compaction: replaced full "
            f"{record['action']} result from step "
            f"{record['step']} with summary "
            f"(original ~{original_length} chars, "
            f"summary ~{len(new_content)} chars)."
        )
        if observability is not None:
            observability.record_compaction(
                turn_number=turn_number,
                step_number=step_number,
                original_length=original_length,
                summary_length=len(new_content),
                action=record["action"],
            )

        if ui_reporter is not None:
            ui_reporter.report(
                "compaction",
                turn=turn_number,
                step=step_number,
                action=record["action"],
                original_chars=original_length,
                summary_chars=len(new_content),
            )


# ==========================================
# 2.6 Agent response normalization
# ==========================================
#
# Some providers occasionally wrap action parameters in a
# nested "parameters" object instead of returning them at
# the top level of the decision, e.g.:
#
#   {"action": "create_node", "parameters": {...}, "reason": "..."}
#
# instead of the canonical:
#
#   {"action": "create_node", ...fields..., "reason": "..."}
#
# This is a known, structurally recoverable envelope
# variation, not a licence to repair arbitrary malformed
# JSON. This step ONLY flattens that one shape. It never
# invents values, fixes misspelled keys, or infers missing
# parameters - anything it can't resolve unambiguously is
# raised as an AgentResponseNormalizationError so the loop
# treats it exactly like a failed AgentDecision validation.
#
# This runs before strict Pydantic validation, for every
# provider equally - it is not conditional on
# MODEL_PROVIDER.


class AgentResponseNormalizationError(ValueError):
    """
    Raised when a response looks like the known nested
    'parameters' envelope but can't be flattened safely -
    e.g. 'parameters' is present but isn't a JSON object, or
    a field is duplicated at both the top level and inside
    'parameters' with two different values. Kept distinct
    from pydantic.ValidationError so the agent loop can
    report normalization failures with their own clear
    message instead of lumping them in with schema errors.
    """

    pass


def normalize_agent_response(
    raw_response: str,
) -> str:

    try:

        parsed = json.loads(
            raw_response
        )

    except json.JSONDecodeError as e:

        raise AgentResponseNormalizationError(
            "Model response was not valid JSON: "
            + str(e)
        ) from e

    if not isinstance(
        parsed,
        dict,
    ):

        # Not a JSON object at all. Nothing for this step
        # to normalize - let strict AgentDecision
        # validation reject it with its own clear error.

        return json.dumps(
            parsed
        )

    # Deterministic repair: some providers occasionally
    # omit the mandatory `reason` field on an otherwise
    # valid decision (observed live with glm-4.7-flash).
    # The reason is conversational context, not safety-
    # relevant data, so a clear placeholder is injected
    # instead of failing the whole step. Any OTHER
    # missing field still fails strict validation.

    if "action" in parsed:

        raw_reason = parsed.get("reason")

        reason_is_missing = (
            raw_reason is None
            or (
                isinstance(raw_reason, str)
                and not raw_reason.strip()
            )
        )

        if reason_is_missing:

            parsed["reason"] = (
                "(no reason provided by the model)"
            )

            logger.info(
                "Agent decision normalization: injected "
                "placeholder for missing 'reason' field."
            )

    if "parameters" not in parsed:

        # No nested envelope present. Return unchanged
        # (re-serialized, but semantically identical -
        # key order does not affect Pydantic validation).

        return json.dumps(
            parsed
        )

    nested_parameters = parsed[
        "parameters"
    ]

    if not isinstance(
        nested_parameters,
        dict,
    ):

        raise AgentResponseNormalizationError(
            "Model response contained a 'parameters' "
            "field that was not a JSON object (got "
            f"{type(nested_parameters).__name__}). "
            "Refusing to guess its intended structure."
        )

    normalized = dict(
        parsed
    )

    del normalized[
        "parameters"
    ]

    conflicting_keys = []

    for key, nested_value in (
        nested_parameters.items()
    ):

        if key in normalized:

            if normalized[key] != nested_value:

                # Same field present at both levels with
                # two different values. Do not silently
                # pick one - surface this as invalid.

                conflicting_keys.append(
                    key
                )

            # Identical duplicate: deliberately keep the
            # existing top-level value and discard the
            # nested copy. (Documented behavior, not an
            # accident of dict iteration order.)

            continue

        normalized[key] = (
            nested_value
        )

    if conflicting_keys:

        raise AgentResponseNormalizationError(
            "Model response had conflicting top-level "
            "and 'parameters' values for field(s): "
            + ", ".join(
                sorted(
                    conflicting_keys
                )
            )
            + ". Refusing to silently choose one."
        )

    logger.info(
        "Agent decision normalization: flattened nested "
        "'parameters' object into top-level action fields."
    )

    return json.dumps(
        normalized
    )


# ==========================================
# 3. Unified model interface
# ==========================================


def _is_transient_provider_error(error) -> bool:
    """Best-effort classification of retryable provider
    failures: HTTP 429 (rate limit) and 5xx statuses
    surfaced through provider error messages. Deterministic,
    bounded (one retry), and never retries auth or schema
    errors."""

    message = str(error)

    for token in ("429", "503", "502", "504", "overloaded"):

        if token in message.lower():
            return True

    return False


def ask_model(
    conversation,
    observability=None,
    turn_number=0,
    step_number=0,
):

    schema = (
        AGENT_DECISION_ADAPTER.json_schema()
    )

    providers = {
        "ollama": (ask_ollama, OLLAMA_MODEL),
        "gemini": (ask_gemini, GEMINI_MODEL),
        "groq": (ask_groq, GROQ_MODEL),
        "openrouter": (ask_openrouter, OPENROUTER_MODEL),
        "zai": (ask_zai, ZAI_MODEL),
    }

    # The panel's model selector overrides provider and
    # model per turn; None falls back to the configured
    # MODEL_PROVIDER and its default model.

    active_provider = (
        ACTIVE_PROVIDER
        if ACTIVE_PROVIDER in providers
        else MODEL_PROVIDER
    )

    provider_call = providers.get(active_provider)

    if provider_call is None:
        raise ValueError(
            "Unknown model provider: " + str(active_provider)
        )

    provider, model = provider_call

    if ACTIVE_MODEL:
        model = ACTIVE_MODEL

    call_id = str(uuid.uuid4())[:8]
    started_at = time.time()
    started_monotonic = time.monotonic()
    # Uniform transient-error retry: provider adapters
    # have heterogeneous internal retry policies (the
    # Groq SDK and the Gemini adapter retry 429/503
    # themselves; Z.ai and OpenRouter do not), so the
    # loop applies one bounded retry here for transient
    # failures regardless of provider. A retry that
    # itself fails records one failed model call and
    # propagates, as before.

    last_error = None

    for attempt in range(2):

        try:
            response = provider(
                conversation=conversation,
                schema=schema,
            )
            result = (
                response
                if isinstance(response, ProviderResult)
                else ProviderResult(text=response)
            )
            break
        except Exception as error:

            last_error = error

            if attempt == 0 and _is_transient_provider_error(
                error
            ):
                logger.warning(
                    "Transient provider error (attempt 1), "
                    + "retrying: "
                    + safe_error_message(error)
                )
                time.sleep(2.0)
                continue

            if observability is not None:
                observability.record_model_call(
                    call_id=call_id,
                    turn_number=turn_number,
                    step_number=step_number,
                    provider=active_provider,
                    model=model,
                    duration_ms=(time.monotonic() - started_monotonic) * 1000,
                    usage=TokenUsage(),
                    success=False,
                    started_at=started_at,
                    error=safe_error_message(error),
                )
            raise

    duration_ms = (time.monotonic() - started_monotonic) * 1000

    if observability is not None:
        observability.record_model_call(
            call_id=call_id,
            turn_number=turn_number,
            step_number=step_number,
            provider=active_provider,
            model=model,
            duration_ms=duration_ms,
            usage=result.usage,
            success=True,
            started_at=started_at,
        )
        logger.info(
            "Model call completed: provider=%s model=%s duration=%.1fms "
            "input_tokens=%s output_tokens=%s total_tokens=%s",
            active_provider,
            model,
            duration_ms,
            result.usage.input_tokens
            if result.usage.available else "unknown",
            result.usage.output_tokens
            if result.usage.available else "unknown",
            result.usage.total_tokens
            if result.usage.available else "unknown",
        )
    return result.text


# ==========================================
# 4. Temporary prototype tools
# ==========================================
#
# describe_current_scene is a temporary prototype action with no
# Godot endpoint; its handler lives in agent/registry.py.


# ==========================================
# 4.5 Action dispatch
# ==========================================
#
# execute_single_action() is the exact same dispatch logic
# that previously lived inline in the agent loop, moved into
# a function with no behavior change. This is what makes
# batching safe without duplicating the tool system: a batch
# item is just an AgentDecision-shaped object (validated by
# the same validate_agent_action() and apply_request_
# constraints() used for a standalone decision) executed
# through this exact same function.


def execute_single_action(
    decision,
    observability=None,
    turn_number=0,
    step_number=0,
    model_call_id=None,
    batch_context=None,
):
    started = time.monotonic()

    tool_started_fields = {
        "turn": turn_number,
        "step": step_number,
        "action": str(decision.action),
    }

    if batch_context is not None:
        tool_started_fields["batch_index"] = batch_context[
            "index"
        ]
        tool_started_fields["batch_size"] = batch_context[
            "total"
        ]

    UI_REPORTER.report(
        "tool_started",
        **tool_started_fields,
    )

    # Approval gate: when enabled, every mutation pauses
    # here and waits (bounded) for the user's decision in
    # the panel. The mutation executes only on approval;
    # a denial becomes a structured failure the model can
    # observe and react to.

    if (
        _ui_settings.APPROVAL_MODE == "mutations"
        and is_mutation_action(decision.action)
    ):

        from agent import bridge_input as _bridge_input

        approval_id = str(uuid.uuid4())[:8]

        UI_REPORTER.report(
            "approval_requested",
            turn=turn_number,
            step=step_number,
            approval_id=approval_id,
            action=str(decision.action),
        )

        approved = False
        decision_received = False
        waited_s = 0.0

        while waited_s < 600.0:

            poll = _bridge_input.fetch_approval()

            if poll["reachable"] and poll["pending"]:
                approved = poll["approved"]
                decision_received = True
                break

            time.sleep(0.5)
            waited_s += 0.5

        UI_REPORTER.report(
            "approval_decision",
            turn=turn_number,
            step=step_number,
            action=str(decision.action),
            approved=approved,
            timed_out=not decision_received,
        )

        if not (decision_received and approved):

            denial = (
                "Denied by the user in the panel."
                if decision_received
                else "Approval wait timed out after "
                + "600 s; treated as denial."
            )

            return {
                "success": False,
                "action": str(decision.action),
                "error": denial,
                "approval_denied": True,
                "message": (
                    "The mutation was not executed. Ask "
                    + "the user how to proceed or choose "
                    + "a different approach."
                ),
            }

    try:
        result = _execute_single_action(decision)
    except Exception as error:
        if observability is not None:
            observability.record_tool_action(
                turn_number=turn_number,
                step_number=step_number,
                action=decision.action,
                success=False,
                duration_ms=(time.monotonic() - started) * 1000,
                model_call_id=model_call_id,
            )
        UI_REPORTER.report(
            "tool_finished",
            turn=turn_number,
            step=step_number,
            action=str(decision.action),
            success=False,
            duration_ms=round(
                (time.monotonic() - started) * 1000, 1
            ),
            error=type(error).__name__,
        )
        raise

    if observability is not None:
        success = (
            bool(result.get("success"))
            if isinstance(result, dict)
            else True
        )
        observability.record_tool_action(
            turn_number=turn_number,
            step_number=step_number,
            action=decision.action,
            success=success,
            duration_ms=(time.monotonic() - started) * 1000,
            model_call_id=model_call_id,
        )

        if is_mutation_action(decision.action):
            mutation_record = build_mutation_record(
                decision,
                result,
                turn_number=turn_number,
                step_number=step_number,
                duration_ms=(time.monotonic() - started) * 1000,
            )
            observability.record_mutation(
                mutation_record,
                model_call_id=model_call_id,
            )
            if mutation_record.contract_violation:
                logger.warning(
                    "Mutation contract violation for %s: %s",
                    decision.action,
                    mutation_record.contract_violation,
                )
            else:
                logger.info(
                    "Mutation recorded: action=%s success=%s "
                    "verification=%s undoable=%s",
                    mutation_record.action,
                    mutation_record.success,
                    mutation_record.verification,
                    mutation_record.undoable,
                )

    if isinstance(result, dict):
        tool_success = bool(result.get("success"))
        tool_error = result.get("error") or result.get(
            "validation_error"
        )
        tool_detail = result.get("message") or ""
    else:
        tool_success = True
        tool_error = None
        tool_detail = ""

    tool_finished_fields = {
        "turn": turn_number,
        "step": step_number,
        "action": str(decision.action),
        "success": tool_success,
        "duration_ms": round(
            (time.monotonic() - started) * 1000, 1
        ),
        "is_mutation": is_mutation_action(decision.action),
        "detail": str(tool_detail)[:200],
    }

    if batch_context is not None:
        tool_finished_fields["batch_index"] = batch_context[
            "index"
        ]
        tool_finished_fields["batch_size"] = batch_context[
            "total"
        ]

    if tool_error:
        tool_finished_fields["error"] = str(tool_error)[:200]

    if is_mutation_action(decision.action) and isinstance(
        result, dict
    ):
        tool_finished_fields["verification"] = (
            classify_verification(result)
        )
        tool_finished_fields["undoable"] = result.get(
            "undoable"
        )
        target = extract_mutation_target(decision)
        if target[1]:
            tool_finished_fields["target"] = "; ".join(
                f"{key}={value}"
                for key, value in target[1]
            )
            if len(target[1]) == 1:
                only_value = target[1][0][1]
                if isinstance(only_value, str) and only_value:
                    tool_finished_fields["target_path"] = only_value
        elif decision.action == "create_node":
            # create_node has no pre-existing mutation
            # target by design, but the ledger should
            # still show WHAT was created.
            parent = getattr(decision, "parent_path", "")
            name = getattr(decision, "node_name", "")
            tool_finished_fields["target"] = (
                f"{parent}/{name}"
                if parent not in ("", ".")
                else str(name)
            )

    UI_REPORTER.report(
        "tool_finished",
        **tool_finished_fields,
    )

    return result


def _execute_single_action(
    decision,
):
    """
    Dispatch a validated, non-control action through the
    agent/registry.py action registry.

    Control actions (batch, final_answer, exit_session) never
    reach this function: final_answer and exit_session are
    intercepted in the main loop, and batch decisions are
    orchestrated by execute_batch_actions().
    """

    spec = ACTION_REGISTRY.get(
        decision.action
    )

    if (
        spec is None
        or spec.handler is None
    ):

        return {
            "success": False,
            "error": (
                "Invalid agent action: "
                + str(
                    decision.action
                )
            ),
        }

    return spec.handler(decision)


def execute_batch_actions(
    decision,
    request,
    logger,
    observability=None,
    turn_number=0,
    step_number=0,
    model_call_id=None,
):
    """
    Execute a validated BatchAction's sub-actions strictly in
    order, through the same apply_request_constraints() ->
    validate_agent_action() -> execute_single_action() path
    used for a standalone decision. Stops immediately on the
    first invalid or failed sub-action; any remaining
    sub-actions are recorded as skipped, never executed and
    never silently dropped from the result.

    Returns one consolidated result dict, in the same general
    shape as any other tool result (it has "success" and
    "message"), so the rest of the agent loop - conversation
    history, execution_result_records, context compaction -
    handles it exactly like any other tool result with no
    special-casing required.
    """

    total = len(
        decision.actions
    )
    started = time.monotonic()

    logger.info(
        f"Batch decision received: {total} action(s)."
    )

    print(
        f"\n--- Executing batch of {total} action(s) ---"
    )

    results = []

    stopped_early = False
    stopped_at_index = None
    succeeded_count = 0

    for index, sub_action in enumerate(
        decision.actions,
        start=1,
    ):

        if stopped_early:

            results.append(
                {
                    "index": index,
                    "action": sub_action.action,
                    "success": False,
                    "skipped": True,
                    "reason": (
                        "Skipped because an earlier "
                        "action in this batch failed."
                    ),
                }
            )

            continue

        print(
            f"\n  [{index}/{total}] "
            f"{sub_action.action}"
        )

        logger.info(
            f"Batch item {index}/{total}: "
            f"executing {sub_action.action}."
        )

        sub_action = (
            apply_request_constraints(
                sub_action,
                request,
            )
        )

        (
            sub_action_is_valid,
            sub_validation_error,
        ) = validate_agent_action(
            sub_action
        )

        if not sub_action_is_valid:

            if observability is not None:
                observability.record_tool_action(
                    turn_number=turn_number,
                    step_number=step_number,
                    action=sub_action.action,
                    success=False,
                    duration_ms=0.0,
                    model_call_id=model_call_id,
                )

            print(
                "  -> validation failed: "
                f"{sub_validation_error}"
            )

            logger.warning(
                f"Batch item {index}/{total} "
                f"({sub_action.action}) failed "
                f"validation: {sub_validation_error}"
            )

            results.append(
                {
                    "index": index,
                    "action": sub_action.action,
                    "success": False,
                    "skipped": False,
                    "validation_error": (
                        sub_validation_error
                    ),
                }
            )

            stopped_early = True
            stopped_at_index = index

            continue

        sub_tool_result = (
            execute_single_action(
                sub_action,
                observability=observability,
                turn_number=turn_number,
                step_number=step_number,
                model_call_id=model_call_id,
                batch_context={
                    "index": index,
                    "total": total,
                },
            )
        )

        print(
            f"  -> {sub_tool_result}"
        )

        sub_success = bool(
            sub_tool_result.get(
                "success"
            )
        )

        results.append(
            {
                "index": index,
                "action": sub_action.action,
                "success": sub_success,
                "skipped": False,
                "tool_result": sub_tool_result,
            }
        )

        if sub_success:

            succeeded_count += 1

            logger.info(
                f"Batch item {index}/{total}: "
                f"{sub_action.action} succeeded."
            )

        else:

            logger.warning(
                f"Batch item {index}/{total} "
                f"({sub_action.action}) failed: "
                f"{sub_tool_result.get('error')}"
            )

            stopped_early = True
            stopped_at_index = index

    all_succeeded = (
        not stopped_early
        and succeeded_count == total
    )

    if all_succeeded:

        message = (
            f"Batch completed: {succeeded_count}/"
            f"{total} action(s) succeeded."
        )

        logger.info(
            "Batch completed successfully: "
            f"{succeeded_count}/{total}."
        )

    else:

        skipped_count = (
            total
            - stopped_at_index
        )

        message = (
            "Batch stopped at action "
            f"{stopped_at_index}/{total} after a "
            f"failure; {skipped_count} action(s) "
            "were skipped. Review the failed "
            "action's details before retrying or "
            "choosing a recovery step."
        )

        logger.warning(
            "Batch stopped early at item "
            f"{stopped_at_index}/{total}. "
            f"{skipped_count} action(s) skipped."
        )

    print(
        f"\n--- Batch finished: {message} ---"
    )

    failed_count = sum(
        1
        for result in results
        if not result.get("success") and not result.get("skipped")
    )
    batch_result = {
        "action": "batch",
        "success": all_succeeded,
        "batch_size": total,
        "succeeded_count": succeeded_count,
        "failed_count": failed_count,
        "stopped_early": stopped_early,
        "stopped_at_index": stopped_at_index,
        "results": results,
        "message": message,
    }
    if observability is not None:
        observability.record_batch(
            turn_number=turn_number,
            step_number=step_number,
            batch_size=total,
            succeeded_count=succeeded_count,
            failed_count=failed_count,
            stopped_early=stopped_early,
            stopped_at_index=stopped_at_index,
            duration_ms=(time.monotonic() - started) * 1000,
            success=all_succeeded,
        )
    return batch_result


# ==========================================
# 5. Logging initialization
# ==========================================

session_id = str(
    uuid.uuid4()
)[:8]

observability = SessionObservability(session_id)

# UI event reporter: pushes agent-state events to the Godot
# editor plugin's bottom panel (POST /agent_event). Strictly
# fire-and-forget; see agent/ui_reporter.py. Referenced via the
# module attribute at every hook site so tests can patch it.

import config.settings as _ui_settings

from agent.ui_reporter import UiReporter

UI_REPORTER = UiReporter()

_UI_MODEL_LABELS = {
    "gemini": getattr(_ui_settings, "GEMINI_MODEL", "gemini"),
    "groq": getattr(_ui_settings, "GROQ_MODEL", "groq"),
    "ollama": getattr(_ui_settings, "OLLAMA_MODEL", "ollama"),
    "openrouter": getattr(
        _ui_settings, "OPENROUTER_MODEL", "openrouter"
    ),
    "zai": getattr(_ui_settings, "ZAI_MODEL", "zai"),
}

UI_MODEL_LABEL = str(
    _UI_MODEL_LABELS.get(
        MODEL_PROVIDER, MODEL_PROVIDER
    )
)

# Models offered in the panel's selector: every provider's
# configured model. The panel can switch provider+model for
# the NEXT turn via the bridge input channel.

UI_AVAILABLE_MODELS = [
    {"provider": provider_key, "model": str(model_name)}
    for provider_key, model_name in (
        ("gemini", _UI_MODEL_LABELS.get("gemini")),
        ("zai", _UI_MODEL_LABELS.get("zai")),
        ("groq", _UI_MODEL_LABELS.get("groq")),
        ("openrouter", _UI_MODEL_LABELS.get("openrouter")),
        ("ollama", _UI_MODEL_LABELS.get("ollama")),
    )
    if model_name
]

# Per-turn provider/model override (None = use the
# configured MODEL_PROVIDER). Applied from the panel's
# model selector via the bridge input channel; all
# provider adapters share the (conversation, schema)
# contract, so switching per turn is structurally safe.

ACTIVE_PROVIDER = None

ACTIVE_MODEL = None

_KNOWN_PROVIDERS = (
    "gemini", "groq", "zai", "openrouter", "ollama",
)

# Input mode: "stdin" (classic CLI) or "bridge" (the Godot
# panel's input box drives the agent; python polls
# GET /agent_input). Selected via AGENT_INPUT_MODE.

AGENT_INPUT_MODE = os.environ.get(
    "AGENT_INPUT_MODE", "stdin"
).strip().lower()


def apply_ui_model_selection(
    selected_provider,
    selected_model,
):
    global ACTIVE_PROVIDER, ACTIVE_MODEL, UI_MODEL_LABEL

    if selected_provider in _KNOWN_PROVIDERS:
        ACTIVE_PROVIDER = selected_provider

    if selected_model:
        ACTIVE_MODEL = selected_model

    if ACTIVE_MODEL:
        UI_MODEL_LABEL = str(ACTIVE_MODEL)


def read_user_request():
    """
    One user request as a (text, mode) tuple.

    mode is "plan" or "act": the user's choice for THIS
    turn. stdin mode parses a leading "/plan " prefix
    (the rest is the request); bridge mode takes the mode
    from the panel's Plan/Act toggle. Applies any model
    selection observed in bridge mode.
    """

    if AGENT_INPUT_MODE != "bridge":

        raw = input(
            "What would you like the Godot assistant "
            "to do? "
        )

        if raw.startswith("/plan ") or raw == "/plan":

            plan_text = raw[len("/plan"):].strip()

            if plan_text:
                return plan_text, "plan"

            print(
                "Note: '/plan' needs a request after it, "
                "e.g. '/plan add three enemy nodes'. "
                "Running in act mode."
            )

        return raw, "act"

    from agent.bridge_input import read_request

    result = read_request()

    apply_ui_model_selection(
        result["selected_provider"],
        result["selected_model"],
    )

    mode = (
        "plan"
        if result["mode"].strip().lower() == "plan"
        else "act"
    )

    return result["text"], mode


def mode_directive(mode):
    """
    The per-turn MODE block appended to the user turn
    message. PLAN mode is enforced deterministically in
    the loop: mutations and file creation are refused
    before execution; the agent is expected to inspect,
    reason, and return its workflow plan via final_answer.
    """

    if mode == "plan":

        return (
            "TURN MODE: PLAN.\n"
            "In this turn you are PLANNING, not acting. "
            "Do not attempt any mutation, file creation, "
            "or scene change - the host will refuse them. "
            "You MAY use read-only inspection actions to "
            "ground the plan in real project state. When "
            "the plan is ready, return it with "
            "final_answer as a numbered, concrete workflow "
            "(exact actions, paths, and values). The user "
            "will switch to Act mode and ask you to carry "
            "this plan out."
        )

    return "TURN MODE: ACT."


UI_REPORTER.report(
    "session_started",
    session_id=session_id,
    model=UI_MODEL_LABEL,
    available_models=UI_AVAILABLE_MODELS,
    context_limit=_ui_settings.CONTEXT_LIMIT_TOKENS,
)


logging.basicConfig(
    level=logging.INFO,
    format=(
        "%(asctime)s - %(levelname)s - "
        "[%(session_id)s] - %(name)s - "
        "%(message)s"
    ),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            "agent.log"
        ),
    ],
)


root_logger = (
    logging.getLogger()
)


for handler in root_logger.handlers:

    handler.addFilter(
        SessionIdFilter(
            session_id
        )
    )


logger = logging.getLogger(
    __name__
)


logger.info(
    "Agent session started. "
    f"Provider: {MODEL_PROVIDER}"
)


# ==========================================
# 4.6 exit_session premature-exit guard
# ==========================================
#
# exit_session is a pure termination decision: it performs no tool
# work and must never be treated as evidence that a requested
# action, especially a mutation, was executed. The main loop honors
# it only after at least one tool action has been executed in the
# current turn; otherwise the decision is rejected and the model is
# asked to perform the requested work first. /exit remains the
# human-controlled host-level termination path and is unaffected.


EXIT_SESSION_GUARD_REASON = (
    "exit_session may only terminate the session after the "
    "current turn's requested actions have been executed: no tool "
    "action has been executed in this turn. exit_session performs "
    "no work itself and cannot substitute for any requested "
    "action, including mutations. Execute each requested action "
    "with a tool call first, then select exit_session only after "
    "those tool actions have actually run. If the user simply "
    "wants to end the session, reply with final_answer and tell "
    "the user to type /exit."
)


def exit_session_is_allowed(
    executed_tool_actions_this_turn: int,
) -> bool:
    """Deterministic guard for exit_session.

    exit_session is allowed only when at least one tool action has
    been executed in the current turn, so it cannot replace
    unperformed work or fabricate evidence that work was done.
    """
    return executed_tool_actions_this_turn > 0


def build_premature_exit_session_result() -> dict:
    """Tool-result-shaped observation returned when the model selects
    exit_session before executing any tool action in the current turn.

    Mirrors the validation-failure observation so the rest of the
    loop (conversation history, execution_result_records, context
    compaction) handles it like any other rejected step.
    """
    return {
        "success": False,
        "validation_error": EXIT_SESSION_GUARD_REASON,
        "action": "exit_session",
        "message": (
            "The proposed agent action was not executed. Return "
            "one corrected next AgentDecision based on this "
            "execution result."
        ),
    }


class AgentSession:

    TERMINATION_COMMAND = "/exit"

    def __init__(
        self,
        conversation,
        logger,
        initial_request,
        observability=None,
        initial_mode="act",
    ):
        self.conversation = conversation
        self.logger = logger
        self.current_request = initial_request
        self.current_mode = initial_mode
        self.turn_number = 1
        self.execution_result_records = []
        self.blocked_skipped_actions: list[dict] = []
        self.turn_completed = False
        self.closed = False
        self.observability = observability
        self.summary = None

    def terminate(self, reason="terminated"):

        self.closed = True
        self.turn_completed = False

        UI_REPORTER.report(
            "session_ended",
            reason=str(reason),
            turns_completed=self.turn_number,
        )

        if self.observability is not None:
            self.summary = self.observability.get_summary(
                turns_completed=self.turn_number,
                termination_reason=reason,
            )
            self.logger.info(
                "Session summary: turns=%s steps=%s model_calls=%s "
                "actions=%s succeeded=%s failed=%s batches=%s "
                "batched_actions=%s compactions=%s duration=%.1fms "
                "input_tokens=%s output_tokens=%s total_tokens=%s "
                "usage_unavailable=%s termination=%s",
                self.summary.turns_completed,
                self.summary.agent_steps,
                self.summary.model_calls,
                self.summary.tool_action_count,
                self.summary.successful_action_count,
                self.summary.failed_action_count,
                self.summary.batch_count,
                self.summary.total_batched_actions,
                self.summary.compaction_count,
                self.summary.duration_ms,
                self.summary.total_input_tokens,
                self.summary.total_output_tokens,
                self.summary.total_tokens,
                self.summary.usage_unavailable_count,
                reason,
            )

            export_path = export_session_jsonl(
                self.observability,
                summary=self.summary,
            )

            if export_path is not None:

                self.logger.info(
                    "Session telemetry exported: %s",
                    export_path,
                )

    def begin_next_turn(self):

        try:
            next_request, next_mode = read_user_request()
        except EOFError:
            self.terminate()
            self.logger.info(
                "Agent session terminated: input stream "
                "ended (EOF)."
            )
            return False

        if next_request.strip() == self.TERMINATION_COMMAND:
            self.terminate()
            self.logger.info(
                "Agent session terminated by user."
            )
            return False

        if not next_request.strip():
            self.terminate()
            self.logger.info(
                "Agent session terminated by empty input."
            )
            return False

        self.current_request = next_request
        self.current_mode = next_mode
        self.turn_number += 1

        UI_REPORTER.report(
            "turn_started",
            turn=self.turn_number,
            request_preview=str(next_request)[:120],
            mode=next_mode,
        )

        self.conversation.append(
            {
                "role": "user",
                "content": (
                    "BEGIN ACTIVE USER TURN "
                    + str(self.turn_number)
                    + ".\n"
                    + mode_directive(next_mode)
                    + "\n"
                    + "Previous turns are completed session history. "
                    + "Use their tool results and established entity "
                    + "references when relevant, but do not repeat or "
                    + "re-answer a previous user request or final answer "
                    + "unless this new request explicitly asks for it.\n\n"
                    + "CURRENT USER REQUEST:\n"
                    + next_request
                    + "\n\n"
                    + "Return exactly ONE AgentDecision "
                    + "JSON object for the next step: either "
                    + "one action, or one bounded batch."
                ),
            }
        )
        self.logger.info(
            f"User turn {self.turn_number} "
            f"request: {next_request}"
        )
        return True

    def complete_turn(self, final_decision=None):

        if final_decision is not None:

            self.conversation.append(
                {
                    "role": "assistant",
                    "content": final_decision.model_dump_json(),
                }
            )

            self.conversation.append(
                {
                    "role": "user",
                    "content": (
                        "END OF COMPLETED USER TURN "
                        + str(self.turn_number)
                        + ". The preceding assistant response is the "
                        + "final answer for that turn and is historical "
                        + "context only. Do not repeat it as the answer "
                        + "to a later turn."
                    ),
                }
            )

        self.turn_completed = True

    def iter_steps(self, max_steps):

        while not self.closed:

            for step in range(max_steps):
                self.turn_completed = False
                yield step

                if self.closed:
                    return

                if self.turn_completed:
                    break

            if self.closed:
                break

            if self.turn_completed:
                self.turn_completed = False
                if not self.begin_next_turn():
                    break
                continue

            self.logger.warning(
                "Agent reached maximum step limit "
                f"({max_steps}) without final_answer"
            )

            UI_REPORTER.report(
                "max_steps_reached",
                turn=self.turn_number,
                max_steps=max_steps,
            )
            print(
                "\nAgent stopped because it reached "
                f"the maximum step limit of {max_steps}."
            )

            if not self.begin_next_turn():
                break


# ==========================================
# 6. Get user request
# ==========================================

user_request, first_turn_mode = read_user_request()


logger.info(
    f"User request: {user_request} "
    f"(mode: {first_turn_mode})"
)

# The first turn's request comes from this module-level
# input() (subsequent turns go through begin_next_turn,
# which reports its own turn_started), so turn 1 must
# announce itself here or its chat transcript and
# timeline grouping never start.

UI_REPORTER.report(
    "turn_started",
    turn=1,
    request_preview=str(user_request)[:120],
    mode=first_turn_mode,
)


# ==========================================
# 7. Agent conversation
# ==========================================

conversation = [

    {
        "role": "system",
        "content": f"""
You are an AI assistant helping a developer
work with Godot.

You operate in an iterative agent loop.

The loop works like this:

1. Choose exactly ONE next step: either a single
   action, or one bounded batch of actions (see
   "batch" below).
2. The host validates and executes it.
3. You receive the execution result.
4. Choose the next step the same way.
5. Continue until the task is complete.

Return exactly ONE AgentDecision JSON object and
stop: either one action object, or one batch
object containing an ordered list of actions.

Do not return a bare list or array of decisions.
Do not return explanatory text outside that single
JSON object.

Every response MUST include a non-empty reason
field. The reason must briefly explain why the
selected next step is the appropriate one at this
point. A batch also needs its own reason, and each
action inside a batch needs its own reason too.

Available actions:

1. get_scene_tree

Use when the user genuinely needs the full
hierarchical structure of the current scene.

Optional parameter:

max_depth (1-50; when set, nodes deeper than
this are cut and reported with
children_truncated so a huge scene never
floods the conversation; drill into those
nodes with get_node_children_summary)

2. find_nodes

Use for targeted discovery or verification of
specific nodes.

Optional parameters:

node_name
node_type
parent_path
name_match
include_root
include_subclasses

name_match may be:

exact
contains
starts_with
ends_with

parent_path restricts the search to a specific
node and its descendants.

include_subclasses (default false) makes
node_type also match subclasses - e.g.
node_type "Node2D" with include_subclasses
true finds CharacterBody2D nodes. Without it
only the exact class matches.

Results are bounded; check total_matches and
truncated before assuming the list is
exhaustive.

Unless the scene root is specifically needed,
use include_root = false.

3. get_node_properties

Use when current properties of one specific
node are required.

Required parameter:

node_path

Optional parameter:

property_names (list; returns only the named
properties, reporting each missing name as
not_found - preferred over a full dump when
only a few values matter)

4. get_node_property

Use when ONLY ONE specific property value
from one specific node is required.

Prefer this targeted action over
get_node_properties when you need only a
single property.

Required parameters:

node_path
property_name

5. set_properties

Use when the user explicitly asks to change one
or more properties of an existing node.

Required parameters:

node_path
properties_json

properties_json must be valid serialized JSON
representing a JSON object.

6. create_node

Required parameters:

parent_path
node_type
node_name

7. rename_node

Required parameters:

node_path
new_name

8. delete_node

Required parameter:

node_path

9. reparent_node

Required parameters:

node_path
new_parent_path

10. duplicate_node

Duplicates an existing node including its
subtree, placing the copy under a new parent
with the specified name.

Required parameters:

node_path
new_parent_path
new_name

11. move_child

Moves an existing child within its parent to a
requested sibling index. Use get_scene_tree or
find_nodes first to learn the current child
order; the result reports the verified sibling
order after the move.

Required parameters:

node_path
new_index

12. add_to_group

Adds an existing node to a persistent group.
The result verifies the resulting membership.
Adding a node that is already in the group is
a deterministic no-op success.

Required parameters:

node_path
group_name

13. remove_from_group

Removes an existing node from a persistent
group. The result verifies the resulting
membership. Removing a node that is not in
the group is a deterministic no-op success.

Required parameters:

node_path
group_name

14. list_node_connections

Use to inspect the live signal connections of one
node, in both directions. The result separates
incoming and outgoing connections and reports the
peer node, signal name, method name, and connection
flags. Use this when wiring or auditing signal
connections; use list_node_signals for the signal
definitions themselves.

Required parameter:

node_path

15. connect_signal

Connects a signal on one existing node to a method
on another existing node. The bridge verifies that
the signal exists on the emitter and the method
exists on the target. Connecting an already
connected pair is a deterministic no-op success.
The result verifies the resulting connection.
Callable expressions are not supported: address the
target exactly as node path plus method name.

Required parameters:

node_path
signal_name
target_path
method_name

Optional parameter:

deferred (default false; when true the connection
is made deferred)

16. disconnect_signal

Removes an existing signal connection between two
nodes. Disconnecting a pair that is not connected
is a deterministic no-op success. The result
verifies the resulting disconnection.

Required parameters:

node_path
signal_name
target_path
method_name

17. create_script

Creates a NEW GDScript file in the project with the full
content you provide. The bridge parse-checks the content
BEFORE writing: content that does not parse is never
written to disk. Existing files are never overwritten.
File creation is NOT undoable; the result verifies the
write by reading the file back.

FILE PLACEMENT: never dump new files into the project
root. Match the project's folder conventions (scripts/,
scenes/, resources/, sprites/, ...) - use
list_project_files first if you have not seen the folder
layout. The result flags root-directory placement with
root_directory_hint.

Required parameters:

script_path (res:// path ending in .gd)
content (the complete GDScript source)

18. attach_script

Attaches an existing GDScript resource to an existing
node. Attaching a script the node already has is a
deterministic no-op success. If the node has a different
script attached, the request is refused; use
detach_script first. The result verifies the resulting
attachment.

Required parameters:

node_path
script_path

19. detach_script

Removes the script attached to an existing node.
Detaching a node without a script is a deterministic
no-op success. The undo restores the previous script.
The result verifies the resulting state.

Required parameter:

node_path

20. get_script_content

Use to read the source of a GDScript file from the
project. To learn which script a node uses, inspect the
node with get_node_properties or find_nodes_by_script
first. For LARGE scripts, use the optional line paging
instead of reading the whole file.

Required parameter:

script_path

Optional parameters:

start_line (1-based)
line_count (1-500)

With paging the result reports total_lines and
truncated; combine with replace_in_script anchors to
edit large files in bounded chunks.

21. list_script_diagnostics

Use to parse-check a GDScript file and read the result.
Use it after create_script or before attach_script when
you are unsure about the script's validity. It reports
parse_ok and the Godot error code when parsing fails.

Required parameter:

script_path

22. edit_script

Replaces the ENTIRE content of an existing GDScript file.
The bridge parse-checks the new content BEFORE writing:
content that does not parse is never written, so the file
stays in its previous working state. Replacing with
byte-identical content is a deterministic no-op success.
This action never creates files; use create_script for
new files.

Required parameters:

script_path
content

23. replace_in_script

Performs a deterministic anchored edit inside an existing
GDScript file: old_string must occur EXACTLY ONCE in the
current content and is replaced by new_string. If
old_string is absent but new_string is already present,
the edit is treated as already applied (no-op success).
Ambiguous matches are refused; never guess the current
content - use get_script_content first. The result is
parse-checked before writing.

Required parameters:

script_path
old_string
new_string

24. get_class_documentation

Use to read the structured documentation of one Godot
class from the version-matched bundled reference: brief
description, full description, methods, properties,
signals, constants. Consult this BEFORE writing code
against unfamiliar classes or members.

Required parameter:

class_name

Optional parameter:

sections

25. search_documentation

Use to discover classes and members when the exact name
is unknown. Bounded case-insensitive search across class
names, member names, and documentation text. Results are
ranked and bounded; check total_matches and truncated.

Required parameter:

query

Optional parameter:

limit

26. save_scene

Saves the currently edited scene to its own file on
disk. Requires the running editor. The result verifies
that the file was written.

SAVE DISCIPLINE - do NOT call save_scene after every
mutation. Save ONLY when one of these holds:

- The user explicitly asked to save.
- EVERY mutation the user requested in this turn is
  complete (one single save at the end of the turn,
  never between mutations).
- A following action requires it (open_scene refuses
  while the scene has unsaved changes).

Required parameters: none

27. create_scene

Creates a NEW scene file with a root node of the
requested type. Existing files are never overwritten.
The file is created on disk but NOT opened in the
editor; opening scenes changes the edited-scene context
and is not part of this tool.

FILE PLACEMENT: use the project's folder conventions
(scenes/ for scenes) rather than the project root; use
list_project_files first if you have not seen the
layout. The result flags root-directory placement with
root_directory_hint.

Required parameters:

scene_path (res:// path ending in .tscn)
root_node_type

28. instantiate_scene

Instances an existing scene file as a child of a node in
the currently edited scene, as one undoable action. The
result verifies the instanced child.

Required parameters:

parent_path
scene_path

Optional parameter:

new_name

29. get_scene_dependencies

Reports the external resources and sub-scenes a scene
file depends on. The scene is loaded without being
opened; the currently edited scene is untouched.

Required parameter:

scene_path

30. get_scene_tree_of

Serializes the node tree of any scene file in the
project without opening it. Use for multi-scene
reasoning; prefer get_scene_tree for the currently
edited scene.

Optional parameter:

max_depth (1-50; same depth-bound semantics as
get_scene_tree)

Required parameter:

scene_path

31. list_open_scenes

Lists the scenes currently open in the editor with the
actively edited scene marked. Requires the running
editor.

Required parameters: none

32. get_property_info

Reports type, hint, usage, current value, and class
default for ONE property of a node. Use this BEFORE
set_properties to learn the expected value shape instead
of guessing the property schema.

Required parameters:

node_path
property_name

33. get_node_children_summary

Lightweight child listing for one node: name, type,
sibling index, child count. Preferred over
get_scene_tree for large scenes when only immediate
children are needed.

Required parameter:

node_path

34. assign_resource_to_property

Loads a res:// resource and assigns it to one property
of a node as a single undoable action. The bridge
verifies the resource loads and the property exists.
The result verifies the assignment by reading the
property back.

Required parameters:

node_path
property_name
resource_path

35. get_resource_info

Reports the type and identity of a resource file (class,
resource path, resource name) from the real loaded
resource.

Required parameter:

resource_path

36. list_project_files

Bounded, filterable listing of project files under a
res:// prefix, optionally restricted to extensions.
Editor-internal directories are excluded. Check
total_matches and truncated before assuming the list is
exhaustive.

Optional parameters:

prefix
extensions
limit

37. search_in_files

Bounded case-insensitive text search across project text
files, optionally restricted to extensions. Results
include file path, line number, and a bounded snippet.
Check total_matches and truncated.

Required parameter:

query

Optional parameters:

extensions
limit

38. get_global_class_list

Lists the project's class_name globals with the script
path that declares each one.

Required parameters: none

39. get_input_map

Reports the project's configured input actions and their
events. Read-only.

Required parameters: none

40. run_scene

Runs the game from the editor (visible to the human in
the editor). Without scene_path the project's MAIN scene
runs; with a scene_path that scene runs instead. Use
stop_run to end the game. To READ the game's output and
errors yourself, use run_scene_offline instead. Requires
the running editor.

Optional parameter:

scene_path

41. stop_run

Stops the game currently run from the editor. The result
verifies that nothing is playing afterwards. Requires the
running editor.

Required parameters: none

42. get_runtime_output

Reads entries captured from custom debugger captures of
a game run via run_scene. NOTE: the engine's built-in
output/error messages are consumed by the editor's own
debugger and do NOT appear here. To read a scene's
output and errors autonomously, use run_scene_offline.

Optional parameter:

clear

43. open_scene

Opens a scene file, making it the edited scene. After
opening, node paths from the previous scene are INVALID;
re-inspect with find_nodes or get_scene_tree. The bridge
refuses to open while the current scene has unsaved
changes (save_scene first). Requires the running editor.

Required parameter:

scene_path

44. save_scene_as

Saves the currently edited scene to a NEW res:// path.
The scene's file path changes to the new location.
Requires the running editor.

Required parameter:

scene_path

45. set_project_settings

Sets one or more project settings (e.g. display/window
size, physics values) in the live ProjectSettings.
settings_json must be a JSON object mapping canonical
setting keys to values. The result reports each key's
previous value so the human can revert, and verifies the
new values by reading them back. Sensitive keys are
rejected.

Required parameter:

settings_json (serialized JSON object)

46. create_resource

Creates a NEW file-backed .tres resource of the requested
Resource type with the given properties (same
serialization rules as set_properties). Existing files
are never overwritten. The result verifies by loading
the resource back.

FILE PLACEMENT: use the project's folder conventions
(resources/, sprites/, materials/, ...) rather than the
project root; use list_project_files first if you have
not seen the layout. The result flags root-directory
placement with root_directory_hint.

Required parameters:

resource_path (res:// path ending in .tres)
resource_type (a Resource class, e.g. Curve)
properties_json (serialized JSON object)

47. run_scene_offline

Runs a scene as a HEADLESS process (not in the editor)
and returns its exit code, stdout, and stderr. This is
the autonomous playtest tool: after creating or editing
scripts and scenes, run the scene offline to check for
SCRIPT ERROR entries and verify behavior, then fix and
re-run. A scene that never exits is killed at the
timeout and reported as timed out.

Required parameter:

scene_path

Optional parameters:

timeout (seconds, 1-120, default 30)
max_output_chars (500-50000; bounds stdout and
stderr per stream, keeping the TAIL where
script errors appear; default 8000)

48. validate_node_type

Use before create_node whenever you are not
completely certain that a Godot class name is
a valid, instantiable node type. Do not guess
class names or retry failed create_node calls
with different spellings.

Required parameter:

node_type

The result states whether the name exists as a
Godot class, whether it is a Node class, and
whether it can be instantiated directly. A type
that exists but is not a Node class (for example
Resource) or cannot be instantiated directly
(for example CanvasItem) is reported as not
valid for node creation.

49. list_available_node_types

Use to discover native, instantiable Godot Node
types before validating an exact candidate or
calling create_node.

Optional parameters:

inherits_from
name_contains
limit

Results contain sorted type names only. They are
bounded (50 by default; 100 maximum), so inspect
total_matches and truncated before assuming the
list is exhaustive. Use validate_node_type on a
chosen exact name before create_node when needed.

50. get_node_class_info

Use to inspect one registered Godot class. The
result includes its direct base class and whether
Godot can instantiate it. This is read-only and
does not require a scene node path.

Required parameter:

class_name

51. list_node_signals

Use to inspect the signals exposed by one node.
The result includes built-in and inherited signal
definitions, not connection state.

Required parameter:

node_path

52. list_node_groups

Use to inspect the groups that one node currently
belongs to. Group membership is instance state and
the result is sorted.

Required parameter:

node_path

53. count_nodes

Use when only the number of matching nodes is
needed. It shares find_nodes filters (including
include_subclasses) and returns the count
without returning the node list.

Optional parameters:

node_name
node_type
parent_path
name_match
include_subclasses

54. find_nodes_by_script

Use to find nodes with an exact attached script
resource path. A missing res:// prefix is normalized.

Required parameter:

script_path

55. find_nodes_by_group

Use to find nodes with exact, case-sensitive live
membership in one group. Zero matches is a success.

Required parameter:

group_name

56. get_project_settings

Use to inspect project configuration from live
ProjectSettings. Provide exact setting names and/or
a bounded non-empty prefix; an unfiltered request is
rejected to avoid a settings dump.

Optional parameters:

setting_names
prefix
limit

57. list_autoloads

Use to list configured project autoload names and
resource targets. It reads live ProjectSettings,
returns deterministic ordering, and is read-only.

58. get_editor_state

Use to inspect bounded current editor state,
including the edited scene, open scenes, selected
nodes, and playing-scene state. It requires the
running editor plugin and does not scrape UI text.

59. list_scenes_in_project

Use to list scene resources known to the running
editor filesystem. Results are sorted and the tool
reports an explicit not-ready error while scanning
or importing.

60. get_undo_history_summary

Use to inspect whether editor undo or redo is
available and to read stable action labels. It is
read-only; never use it to perform undo or redo.

61. describe_current_scene

Use only when visual information is necessary.

62. final_answer

Use only when the informational request has been
answered or every requested operation has been
completed for the current user turn.

final_answer ends only the current turn. The session
remains alive and will prompt for another user turn.

Required parameter:

final_answer

63. exit_session

Use only when the entire persistent session is
explicitly complete or genuinely unrecoverable.

exit_session ends the whole session. No further user
turns will be prompted.

Do NOT use exit_session merely because the current
task is complete and the user may reasonably continue
working in the same session. Use final_answer for
normal turn completion.

exit_session performs NO tool work itself: it never
creates, deletes, renames, inspects, or modifies
anything.

You MUST execute every action the user requested for
the current turn as its own tool action (or batch)
BEFORE selecting exit_session. exit_session cannot
substitute for requested work.

Never claim in exit_summary that any tool action was
performed unless an actual tool result in this
conversation proves it. For example, if you have not
executed delete_node on "Omnitrix", never write that
you deleted it.

If the user asks to end the session but also requests
work, perform all of the requested work first, then
select exit_session only after those tool actions
have actually executed.

Required parameter:

exit_summary

exit_summary must briefly explain why the session is
being terminated.

64. batch

Use only when you are already confident about a
short, strictly sequential series of KNOWN,
deterministic mutations and do not need to inspect
any result in between them.

A batch is a single JSON object:

{{
  "reason": "...",
  "action": "batch",
  "actions": [
    {{ "reason": "...", "action": "create_node", ... }},
    {{ "reason": "...", "action": "rename_node", ... }}
  ]
}}

IMPORTANT BATCH FORMAT:

"actions" MUST be a JSON array of ACTION OBJECTS.

Each array element MUST be a complete action object
with its own "action" field.

CORRECT:

{{
  "action": "batch",
  "actions": [
    {{
      "reason": "Rename Heatblast HP",
      "action": "rename_node",
      "node_path": "Negatrix/Heatblast/HP",
      "new_name": "Health-60"
    }},
    {{
      "reason": "Rename Heatblast Attack",
      "action": "rename_node",
      "node_path": "Negatrix/Heatblast/Attack",
      "new_name": "Attack-100"
    }}
  ]
}}

INCORRECT:

{{
  "action": "batch",
  "actions": [
    "rename_node",
    "node_path",
    "Negatrix/Heatblast/HP",
    "new_name",
    "Health-60"
  ]
}}

Never flatten action objects into a list of strings.
Never put field names or field values directly into
the "actions" array.
The maximum number of elements in "actions" is
{MAX_BATCH_SIZE}.

Rules:

- actions must contain between 1 and
  {MAX_BATCH_SIZE} items.

- Every item in actions must be a complete action
  object: the same shape, fields, and required
  parameters as a normal single-action decision,
  including its own non-empty reason. final_answer
  must never appear inside actions - return
  final_answer or exit_session by itself, as its own
  step, once you are ready to conclude.

- Actions execute strictly in the order listed.

- If any action in the batch fails, execution
  stops immediately. Remaining actions in that
  batch are not executed. You will receive one
  consolidated result showing exactly which
  actions succeeded, which one failed and why, and
  which were skipped, so you can decide how to
  recover.

Good candidates for a batch:

- Creating several new, independently named nodes.
- Renaming a node immediately after creating it in
  the same batch.
- Reparenting a node immediately after creating or
  renaming it in the same batch, when its resulting
  path is already known from that batch.
- Deleting several explicitly identified nodes.

Keep these as separate single-action steps instead
of a batch:

- Inspecting the scene before deciding what to do.
- Any step whose parameters depend on the result of
  a find_nodes or get_scene_tree call you have not
  made yet.
- Recovering after a failure.
- Resolving ambiguous or unknown scene structure.
- Final reasoning based on verification results.

When genuinely unsure, prefer a single action over
a batch. A batch is for mutations you already know
are safe from current context, not a way to plan
further ahead than you can actually verify.

65. scan_project_issues

Scans project files for mechanical problems and
reports them as a bounded, structured issue list:
script_parse_error (.gd files that fail a fresh
parse), scene_load_failed (.tscn files that do
not load), and missing_dependency (scene
dependencies whose res:// path does not exist).
Read-only and editor-independent. Use it after
large refactors, after batch mutations, or
before final_answer to verify the project is
still coherent. Check total_matches, truncated,
and scanned_files before assuming a short issue
list means the whole project was scanned.

Optional parameters:

prefix (res:// sub-path; defaults to the whole
project)
limit (1-100, default 50)

66. rename_script

Renames or moves an existing GDScript file and
updates every textual reference to its res://
path across project files (.gd, .tscn, .tres,
.cfg, project.godot) in one deterministic
operation. Two-phase and parse-gated: if any
affected .gd file would no longer parse, the
whole operation is refused with nothing
written. The target path must not exist; the
.uid sidecar is renamed alongside when present.
The result lists changed files with per-file
reference counts and verifies by re-scanning.
Not undoable. Prefer this over manual
edit_script + replace_in_script chains whenever
a script path changes.

Required parameters:

script_path (existing res:// path ending in .gd)
new_script_path (non-existing res:// path ending in .gd)

67. find_replace_across_files

Replaces every occurrence of old_string with
new_string across multiple project text files in
one deterministic, parse-gated operation. Files
are selected by extensions and an optional
prefix; the result lists each modified file with
its replacement count and verifies by reading
the files back. A request matching more files
than max_files is refused entirely, never
partially applied; if any affected .gd file
would no longer parse, nothing is written.
Not undoable. Use search_in_files first to know
what will match; use replace_in_script instead
when a single script needs a unique-anchor edit.

Required parameters:

old_string (non-empty)
new_string (may be empty to delete occurrences)

Optional parameters:

extensions (default ["gd", "tscn", "tres"])
prefix (res:// sub-path)
max_files (1-50, default 20)

Important rules:

- Each user turn carries a MODE set by the user and
  stated in the turn message: PLAN or ACT. In PLAN
  mode the host refuses every mutation and file
  creation; ground your plan with read-only
  inspections and return it via final_answer. In ACT
  mode you execute normally (carrying out an
  earlier plan counts). You cannot switch modes;
  only the user can.

- Choose exactly one step per response: either one
  action, or one batch.

- Never select an action until every required
  field for that action has been populated.

- Never invent node paths.

- The edited scene root is represented by ".".

- Never use "/root", "/", or an empty string for
  the edited scene root.

- If the target node path is unknown, use
  find_nodes before modifying the node.

- If the user explicitly asks to create, set,
  change, modify, rename, delete, move, reparent,
  or configure something, perform the appropriate
  available tool action.

- Never use final_answer as the first action for
  a modification request when an appropriate tool
  exists.

- After completing all requested changes, use
  final_answer.

- Prefer a targeted tool over a broad one when
  checking a specific fact.

- To verify whether a specific node exists in a
  specific location, prefer find_nodes with an
  appropriate node_name and parent_path instead
  of get_scene_tree.

- Use get_scene_tree only when the full hierarchy
  is actually needed.

- If a mutation result includes explicit
  post-operation verification fields describing
  actual editor state, those fields may be used
  as verification evidence.

- Never claim that something was verified,
  checked, or confirmed unless an actual tool
  result received during this conversation
  supports that claim.

- Remembering that an operation was requested or
  attempted is not the same as verifying its
  outcome.

- When using set_properties, properties_json must
  contain valid serialized JSON only. Do not put
  comments, Markdown, or explanatory text inside
  properties_json.
""",
    },

    {
        "role": "user",
        "content": (
            mode_directive(first_turn_mode)
            + "\n\n"
            + "USER REQUEST:\n"
            + user_request
            + "\n\n"
            + "Return exactly ONE AgentDecision "
            + "JSON object for the next step: either "
            + "one action, or one bounded batch."
        ),
    },

]


session = AgentSession(
    conversation,
    logger,
    user_request,
    observability,
    initial_mode=first_turn_mode,
)


# ==========================================
# 8. Agent loop
# ==========================================

# Session-scoped state is retained across user turns.
execution_result_records = session.execution_result_records
blocked_skipped_actions = session.blocked_skipped_actions

MAX_STEPS = _ui_settings.MAX_STEPS


executed_tool_actions_this_turn = 0


for step in session.iter_steps(
    MAX_STEPS
):

    if step == 0:

        executed_tool_actions_this_turn = 0

    logger.info(
        f"Step {step + 1} of {MAX_STEPS}"
    )

    print(
        f"\n--- Agent step {step + 1} ---"
    )

    try:

        UI_REPORTER.report(
            "request_sent",
            turn=session.turn_number,
            step=step + 1,
            model=UI_MODEL_LABEL,
        )

        raw_response = ask_model(
            conversation,
            observability=observability,
            turn_number=session.turn_number,
            step_number=step + 1,
        )

        model_call_id = (
            observability.model_calls[-1].call_id
            if observability.model_calls
            else None
        )

        last_call = (
            observability.model_calls[-1]
            if observability.model_calls
            else None
        )

        model_response_fields = {
            "turn": session.turn_number,
            "step": step + 1,
            "model": (
                last_call.model if last_call else UI_MODEL_LABEL
            ),
            "duration_ms": round(
                last_call.duration_ms, 1
            )
            if last_call
            else None,
            "prompt_tokens": (
                last_call.usage.input_tokens
                if last_call and last_call.usage.available
                else None
            ),
            "output_tokens": (
                last_call.usage.output_tokens
                if last_call and last_call.usage.available
                else None
            ),
        }

        UI_REPORTER.report(
            "model_response",
            **model_response_fields,
        )

    except Exception as e:

        logger.error(
            "Model provider error: "
            + safe_error_message(e)
        )

        print(
            "\nAgent error: Could not get "
            "response from model provider."
        )

        print(
            f"Error: {type(e).__name__}: "
            f"{str(e)}"
        )

        print(
            f"\nAgent session {session_id} failed."
        )

        UI_REPORTER.report(
            "error",
            context="model_call",
            error=safe_error_message(e)[:200],
        )

        session.terminate("model_call_failed")
        break

    print(
        "\nRaw model response:"
    )

    print(
        repr(
            raw_response
        )
    )

    try:

        normalized_response = (
            normalize_agent_response(
                raw_response
            )
        )

        decision = (
            AGENT_DECISION_ADAPTER.validate_json(
                normalized_response
            )
        )

    except AgentResponseNormalizationError as e:

        logger.error(
            "Agent response normalization error: "
            f"{str(e)[:200]}"
        )

        print(
            "\nAgent error: Model response could not "
            "be safely normalized into an AgentDecision."
        )

        print(
            "Response (first 500 chars):"
        )

        print(
            raw_response[:500]
        )

        print(
            "Normalization error:"
        )

        print(
            str(e)[:500]
        )

        print(
            f"\nAgent session {session_id} failed."
        )

        UI_REPORTER.report(
            "error",
            context="response_normalization",
            error=str(e)[:200],
        )

        session.terminate("response_normalization_failed")
        break

    except ValidationError as e:

        logger.error(
            "Decision validation error: "
            f"{str(e)[:200]}"
        )

        print(
            "\nAgent error: Model response was "
            "not a valid AgentDecision."
        )

        print(
            "Response (first 500 chars):"
        )

        print(
            raw_response[:500]
        )

        print(
            "Validation error:"
        )

        print(
            str(e)[:500]
        )

        print(
            f"\nAgent session {session_id} failed."
        )

        UI_REPORTER.report(
            "error",
            context="decision_validation",
            error=str(e)[:200],
        )

        session.terminate("decision_validation_failed")
        break

    except Exception as e:

        logger.error(
            "Unexpected validation error: "
            f"{type(e).__name__}: {str(e)}"
        )

        print(
            "\nAgent error: Unexpected error "
            "validating model response."
        )

        print(
            f"Error: {type(e).__name__}: "
            f"{str(e)}"
        )

        print(
            f"\nAgent session {session_id} failed."
        )

        UI_REPORTER.report(
            "error",
            context="response_validation",
            error=f"{type(e).__name__}: {str(e)}"[:200],
        )

        session.terminate("response_validation_failed")
        break

    decision = (
        apply_request_constraints(
            decision,
            session.current_request,
        )
    )

    (
        action_is_valid,
        validation_error,
    ) = (
        validate_agent_action(
            decision
        )
    )

    if not action_is_valid:

        UI_REPORTER.report(
            "validation_rejected",
            turn=session.turn_number,
            step=step + 1,
            action=str(decision.action),
            error=str(validation_error)[:200],
        )

        observability.record_tool_action(
            turn_number=session.turn_number,
            step_number=step + 1,
            action=decision.action,
            success=False,
            duration_ms=0.0,
            model_call_id=model_call_id,
        )

        validation_result = {
            "success": False,
            "validation_error": (
                validation_error
            ),
            "action": (
                decision.action
            ),
            "message": (
                "The proposed agent action was "
                "not executed. Return one corrected "
                "next AgentDecision based on this "
                "execution result."
            ),
        }

        print(
            "\nAgent action validation failed:"
        )

        print(
            validation_error
        )

        conversation.append(
            {
                "role": "assistant",
                "content": (
                    decision.model_dump_json()
                ),
            }
        )

        conversation.append(
            {
                "role": "user",
                "content": (
                    "AGENT EXECUTION RESULT FOR "
                    "THE PREVIOUS STEP:\n"
                    + json.dumps(
                        validation_result
                    )
                    + "\n\n"
                    + "The previous step was not "
                    + "executed successfully. "
                    + "Return exactly ONE corrected "
                    + "AgentDecision JSON object for "
                    + "the next step: either one "
                    + "action, or one bounded batch."
                ),
            }
        )

        execution_result_records.append(
            {
                "step": step + 1,
                "action": decision.action,
                "conversation_index": (
                    len(
                        conversation
                    )
                    - 1
                ),
                "tool_result": None,
                "compacted": False,
            }
        )

        compact_conversation(
            conversation,
            execution_result_records,
            logger,
            observability=observability,
            turn_number=session.turn_number,
            step_number=step + 1,
            ui_reporter=UI_REPORTER,
        )

        continue

    UI_REPORTER.report(
        "thinking",
        turn=session.turn_number,
        step=step + 1,
        action=str(decision.action),
        reason=str(decision.reason)[:300],
        prompt_tokens=last_call.usage.input_tokens
        if last_call and last_call.usage.available
        else None,
        output_tokens=last_call.usage.output_tokens
        if last_call and last_call.usage.available
        else None,
    )

    print(
        "\nAgent decision:"
    )

    print(
        decision
    )

    # ----------------------------------------------------------
    # PLAN MODE: when the user launched this turn in plan
    # mode, mutations and file creation are refused here,
    # deterministically, before any execution. Read-only
    # inspections are allowed (planning should be grounded
    # in real state); the expected turn outcome is a
    # workflow plan via final_answer.
    # ----------------------------------------------------------

    if (
        session.current_mode == "plan"
        and decision.action != "final_answer"
        and decision.action != "exit_session"
    ):

        if decision.action == "batch":

            plan_mode_violation = any(
                is_mutation_action(sub_action.action)
                for sub_action in decision.actions
            )

        else:

            plan_mode_violation = is_mutation_action(
                decision.action
            )

        if plan_mode_violation:

            observability.record_tool_action(
                turn_number=session.turn_number,
                step_number=step + 1,
                action=decision.action,
                success=False,
                duration_ms=0.0,
                model_call_id=model_call_id,
            )

            UI_REPORTER.report(
                "attention",
                turn=session.turn_number,
                step=step + 1,
                kind="plan_mode_refusal",
                detail=(
                    "Refused "
                    + str(decision.action)
                    + ": mutations are not allowed in "
                    + "Plan mode."
                )[:200],
            )

            print(
                "\nPLAN MODE REFUSAL: "
                + str(decision.action)
                + " mutates the project and cannot run "
                + "while the user is in Plan mode."
            )

            plan_mode_result = {
                "success": False,
                "action": (
                    decision.action
                ),
                "error": (
                    "Plan mode is active: this action "
                    "mutates the project and was not "
                    "executed. Use read-only inspection "
                    "actions to ground your reasoning and "
                    "return your complete workflow plan "
                    "with final_answer. The user will "
                    "switch to Act mode to execute it."
                ),
                "plan_mode": True,
                "message": (
                    "The proposed agent action was not "
                    "executed. Return one corrected next "
                    "AgentDecision based on this "
                    "execution result."
                ),
            }

            conversation.append(
                {
                    "role": "assistant",
                    "content": (
                        decision.model_dump_json()
                    ),
                }
            )

            conversation.append(
                {
                    "role": "user",
                    "content": (
                        "AGENT EXECUTION RESULT FOR "
                        "THE PREVIOUS STEP:\n"
                        + json.dumps(
                            plan_mode_result
                        )
                        + "\n\n"
                        + "The previous step was not "
                        + "executed successfully. "
                        + "Return exactly ONE corrected "
                        + "AgentDecision JSON object for "
                        + "the next step: either one "
                        + "action, or one bounded batch."
                    ),
                }
            )

            execution_result_records.append(
                {
                    "step": step + 1,
                    "action": decision.action,
                    "conversation_index": (
                        len(
                            conversation
                        )
                        - 1
                    ),
                    "tool_result": None,
                    "compacted": False,
                }
            )

            compact_conversation(
                conversation,
                execution_result_records,
                logger,
                observability=observability,
                turn_number=session.turn_number,
                step_number=step + 1,
                ui_reporter=UI_REPORTER,
            )

            continue

    if (
        decision.action
        == "final_answer"
    ):

        print(
            "\nFinal agent response:"
        )

        print(
            decision.final_answer
        )

        logger.info(
            f"Agent session {session_id} "
            f"completed user turn: {session.current_request}"
        )

        UI_REPORTER.report(
            "turn_completed",
            turn=session.turn_number,
            final_answer=str(decision.final_answer),
        )

        session.complete_turn(decision)
        continue

    if (
        decision.action
        == "exit_session"
    ):

        if (
            not exit_session_is_allowed(
                executed_tool_actions_this_turn
            )
        ):

            logger.warning(
                "BLOCKED PREMATURE exit_session with no "
                "executed tool action in the current turn. "
                "Summary: %s",
                decision.exit_summary,
            )

            UI_REPORTER.report(
                "attention",
                turn=session.turn_number,
                step=step + 1,
                kind="premature_exit_blocked",
                detail=(
                    "exit_session blocked: no tool action "
                    "executed this turn."
                )[:200],
            )

            print(
                "\nPREMATURE EXIT SESSION BLOCKED:"
            )

            print(
                "exit_session cannot substitute for "
                "requested work. No tool action has "
                "been executed in the current turn."
            )

            print(
                decision.exit_summary
            )

            guard_result = (
                build_premature_exit_session_result()
            )

            conversation.append(
                {
                    "role": "assistant",
                    "content": (
                        decision.model_dump_json()
                    ),
                }
            )

            conversation.append(
                {
                    "role": "user",
                    "content": (
                        "AGENT EXECUTION RESULT FOR "
                        "THE PREVIOUS STEP:\n"
                        + json.dumps(
                            guard_result
                        )
                        + "\n\n"
                        + "The proposed exit_session was "
                        + "not accepted because no tool "
                        + "action has been executed in "
                        + "the current turn. If the user "
                        + "requested any work, execute it "
                        + "now with tool actions, and only "
                        + "then select exit_session. If the "
                        + "user simply wants to end the "
                        + "session, reply with final_answer "
                        + "and tell the user to type /exit."
                    ),
                }
            )

            execution_result_records.append(
                {
                    "step": step + 1,
                    "action": decision.action,
                    "conversation_index": (
                        len(
                            conversation
                        )
                        - 1
                    ),
                    "tool_result": None,
                    "compacted": False,
                }
            )

            compact_conversation(
                conversation,
                execution_result_records,
                logger,
                observability=observability,
                turn_number=session.turn_number,
                step_number=step + 1,
                ui_reporter=UI_REPORTER,
            )

            continue

        print(
            "\nSession ended by agent:"
        )

        print(
            decision.exit_summary
        )

        logger.info(
            "Agent session %s terminated by "
            "model decision. Summary: %s",
            session_id,
            decision.exit_summary,
        )

        session.terminate()
        continue

    tool_result = None

    # ----------------------------------------------------------
    # HARD ENFORCEMENT: Block automatic resume of skipped batch
    # actions. This runs in Python before any execution, so it
    # cannot be bypassed by the model ignoring a conversation
    # boundary message.
    # ----------------------------------------------------------
    (
        is_blocked,
        blocked_reason,
        blocked_matches,
    ) = check_decision_blocked(
        decision,
        blocked_skipped_actions,
    )

    if is_blocked:

        observability.record_tool_action(
            turn_number=session.turn_number,
            step_number=step + 1,
            action=decision.action,
            success=False,
            duration_ms=0.0,
            model_call_id=model_call_id,
        )

        logger.warning(
            "BLOCKED AUTOMATIC RESUME: %s",
            blocked_reason,
        )

        UI_REPORTER.report(
            "blocked_action",
            turn=session.turn_number,
            step=step + 1,
            action=str(decision.action),
            reason=str(blocked_reason)[:200],
        )

        print(
            "\nBATCH EXECUTION BOUNDARY: "
            + blocked_reason
        )

        tool_result = {
            "success": False,
            "action": decision.action,
            "error": blocked_reason,
            "message": (
                "This action was blocked because it matches a "
                "skipped action from an earlier interrupted batch. "
                "It will not be automatically executed. Choose a "
                "recovery path: inspect the failure, correct and "
                "explicitly retry the failed action, ask the user "
                "for clarification, or finalize with partial "
                "completion."
            ),
            "blocked_resume": True,
            "blocked_matches": blocked_matches,
        }

    elif (
        decision.action
        == "batch"
    ):

        UI_REPORTER.report(
            "batch_started",
            turn=session.turn_number,
            step=step + 1,
            batch_size=len(decision.actions),
        )

        tool_result = (
            execute_batch_actions(
                decision,
                session.current_request,
                logger,
                observability=observability,
                turn_number=session.turn_number,
                step_number=step + 1,
                model_call_id=model_call_id,
            )
        )

        executed_tool_actions_this_turn += 1

        UI_REPORTER.report(
            "batch_finished",
            turn=session.turn_number,
            step=step + 1,
            batch_size=len(decision.actions),
            success=bool(
                tool_result.get("success")
            )
            if isinstance(tool_result, dict)
            else False,
        )

    else:

        tool_result = (
            execute_single_action(
                decision,
                observability=observability,
                turn_number=session.turn_number,
                step_number=step + 1,
                model_call_id=model_call_id,
            )
        )

        executed_tool_actions_this_turn += 1

    print(
        "\nTool result:"
    )

    print(
        tool_result
    )

    conversation.append(
        {
            "role": "assistant",
            "content": (
                decision.model_dump_json()
            ),
        }
    )

    conversation.append(
        {
            "role": "tool",
            "content": json.dumps(
                tool_result
            ),
        }
    )

    execution_result_records.append(
        {
            "step": step + 1,
            "action": decision.action,
            "conversation_index": (
                len(
                    conversation
                )
                - 1
            ),
            "tool_result": tool_result,
            "compacted": False,
        }
    )

    # If the batch stopped early, enforce an explicit execution
    # boundary. Without this, the model sees the original user
    # request plus the batch result and may incorrectly assume it
    # should automatically resume the skipped actions. This code
    # records the skipped actions in orchestration state
    # (blocked_skipped_actions) so that Python hard-blocks any
    # later attempt to automatically resume them, and appends a
    # conversation message as additional model guidance.
    if (
        decision.action == "batch"
        and isinstance(tool_result, dict)
        and tool_result.get("stopped_early")
    ):
        stopped_at_index = tool_result.get("stopped_at_index")
        total = tool_result.get("batch_size", 0)
        skipped_count = (
            total - stopped_at_index
            if stopped_at_index
            else 0
        )

        failed_action_name = None
        failed_action_error = None
        skipped_descriptions = []

        # Build a lookup from batch result index -> result entry
        # so we can identify which sub-actions were skipped.
        result_by_index = {
            result.get("index"): result
            for result in tool_result.get("results", [])
            if isinstance(result, dict)
        }

        # Extract the actual skipped sub-action objects from the
        # batch decision and record them in blocked_skipped_actions
        # with their equivalence fingerprints. This is what makes
        # the hard enforcement work: Python now knows the exact
        # parameters of each skipped action.
        newly_blocked = 0
        for batch_index, sub_action in enumerate(
            decision.actions,
            start=1,
        ):
            result_entry = result_by_index.get(batch_index)
            if result_entry and result_entry.get("skipped"):
                fingerprint = compute_action_fingerprint(
                    sub_action
                )

                blocked_skipped_actions.append(
                    {
                        "fingerprint": fingerprint,
                        "mutation_target": extract_mutation_target(
                            sub_action
                        ),
                        "action": sub_action.action,
                        "batch_index": batch_index,
                        "batch_size": total,
                    }
                )

                newly_blocked += 1
                skipped_descriptions.append(
                    f"action {batch_index} ({sub_action.action})"
                )
            elif (
                result_entry
                and result_entry.get("index")
                == stopped_at_index
            ):
                failed_action_name = result_entry.get("action")
                tool_result_payload = result_entry.get(
                    "tool_result"
                )
                if isinstance(tool_result_payload, dict):
                    failed_action_error = (
                        tool_result_payload.get("error")
                    )
                if not failed_action_error:
                    failed_action_error = result_entry.get(
                        "validation_error"
                    )

        failed_detail = (
            f"Action {stopped_at_index} ({failed_action_name}) failed"
            + (
                f": {failed_action_error}"
                if failed_action_error
                else "."
            )
        )
        skipped_detail = (
            f"{skipped_count} action(s) were skipped"
            + (
                f": {', '.join(skipped_descriptions)}."
                if skipped_descriptions
                else "."
            )
        )

        boundary_message = (
            "BATCH EXECUTION INTERRUPTED - "
            "EXECUTION BOUNDARY ENFORCED.\n"
            f"{failed_detail}\n"
            f"{skipped_detail}\n\n"
            "CRITICAL: Do NOT automatically execute skipped "
            "actions from this batch in subsequent steps. "
            "The remaining actions from the original request "
            "were intentionally not executed because the "
            "batch was interrupted.\n\n"
            "Choose exactly ONE of the following:\n"
            "1. Analyze the failed action and attempt a "
            "corrected recovery (e.g., find the correct "
            "node, fix the path, then retry).\n"
            "2. Ask the user for clarification.\n"
            "3. Finalize with a partial completion report "
            "describing what succeeded, what failed, and "
            "what was skipped.\n\n"
            "Return exactly ONE AgentDecision JSON object "
            "for the next step."
        )

        print(f"\n{boundary_message}")

        logger.warning(
            "BATCH EXECUTION BOUNDARY: recorded %s skipped "
            "action(s) as blocked from automatic resume. "
            "Failed at action %s/%s.",
            newly_blocked,
            stopped_at_index,
            total,
        )

        logger.warning(
            "Batch execution boundary enforced at action "
            "%s/%s. %s action(s) skipped. Skipped actions "
            "must not be automatically resumed.",
            stopped_at_index,
            total,
            skipped_count,
        )

        conversation.append(
            {
                "role": "user",
                "content": boundary_message,
            }
        )

    compact_conversation(
        conversation,
        execution_result_records,
        logger,
        observability=observability,
        turn_number=session.turn_number,
        step_number=step + 1,
        ui_reporter=UI_REPORTER,
    )

else:

    logger.warning(
        "Agent session closed after the final user turn."
    )

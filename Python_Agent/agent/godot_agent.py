from models.ollama_provider import ask_ollama
from models.gemini_provider import ask_gemini
from models.groq_provider import ask_groq
from models.openrouter_provider import ask_openrouter

from config.settings import (
    MODEL_PROVIDER,
    MAX_BATCH_SIZE,
    GEMINI_MODEL,
    OLLAMA_MODEL,
    OPENROUTER_MODEL,
)
from models.groq_provider import GROQ_MODEL

import json
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
    safe_error_message,
)

from agent.registry import ACTION_REGISTRY


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
    }
    provider_call = providers.get(MODEL_PROVIDER)
    if provider_call is None:
        raise ValueError(
            "Unknown model provider: " + str(MODEL_PROVIDER)
        )

    provider, model = provider_call
    call_id = str(uuid.uuid4())[:8]
    started_at = time.time()
    started_monotonic = time.monotonic()
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
    except Exception as error:
        if observability is not None:
            observability.record_model_call(
                call_id=call_id,
                turn_number=turn_number,
                step_number=step_number,
                provider=MODEL_PROVIDER,
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
            provider=MODEL_PROVIDER,
            model=model,
            duration_ms=duration_ms,
            usage=result.usage,
            success=True,
            started_at=started_at,
        )
        logger.info(
            "Model call completed: provider=%s model=%s duration=%.1fms "
            "input_tokens=%s output_tokens=%s total_tokens=%s",
            MODEL_PROVIDER,
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
):
    started = time.monotonic()
    try:
        result = _execute_single_action(decision)
    except Exception:
        if observability is not None:
            observability.record_tool_action(
                turn_number=turn_number,
                step_number=step_number,
                action=decision.action,
                success=False,
                duration_ms=(time.monotonic() - started) * 1000,
                model_call_id=model_call_id,
            )
        raise

    if observability is not None:
        observability.record_tool_action(
            turn_number=turn_number,
            step_number=step_number,
            action=decision.action,
            success=(
                bool(result.get("success"))
                if isinstance(result, dict)
                else True
            ),
            duration_ms=(time.monotonic() - started) * 1000,
            model_call_id=model_call_id,
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


class AgentSession:

    TERMINATION_COMMAND = "/exit"

    def __init__(
        self,
        conversation,
        logger,
        initial_request,
        observability=None,
    ):
        self.conversation = conversation
        self.logger = logger
        self.current_request = initial_request
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

    def begin_next_turn(self):

        try:
            next_request = input(
                "What would you like the Godot assistant to do? "
            )
        except EOFError:
            self.terminate()
            return False

        if next_request.strip() == self.TERMINATION_COMMAND:
            self.terminate()
            self.logger.info(
                "Agent session terminated by user."
            )
            return False

        if not next_request.strip():
            self.terminate()
            return False

        self.current_request = next_request
        self.turn_number += 1
        self.conversation.append(
            {
                "role": "user",
                "content": (
                    "USER REQUEST:\n"
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

    def complete_turn(self):
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
            print(
                "\nAgent stopped because it reached "
                f"the maximum step limit of {max_steps}."
            )

            if not self.begin_next_turn():
                break


# ==========================================
# 6. Get user request
# ==========================================

user_request = input(
    "What would you like the Godot assistant to do? "
)


logger.info(
    f"User request: {user_request}"
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

2. find_nodes

Use for targeted discovery or verification of
specific nodes.

Optional parameters:

node_name
node_type
parent_path
name_match
include_root

name_match may be:

exact
contains
starts_with
ends_with

parent_path restricts the search to a specific
node and its descendants.

Unless the scene root is specifically needed,
use include_root = false.

3. get_node_properties

Use when current properties of one specific
node are required.

Required parameter:

node_path

4. set_properties

Use when the user explicitly asks to change one
or more properties of an existing node.

Required parameters:

node_path
properties_json

properties_json must be valid serialized JSON
representing a JSON object.

5. create_node

Required parameters:

parent_path
node_type
node_name

6. rename_node

Required parameters:

node_path
new_name

7. delete_node

Required parameter:

node_path

8. reparent_node

Required parameters:

node_path
new_parent_path

9. duplicate_node

Duplicates an existing node including its
subtree, placing the copy under a new parent
with the specified name.

Required parameters:

node_path
new_parent_path
new_name

10. describe_current_scene

Use only when visual information is necessary.

11. final_answer

Use only when the informational request has been
answered or every requested operation has been
completed for the current user turn.

final_answer ends only the current turn. The session
remains alive and will prompt for another user turn.

Required parameter:

final_answer

13. exit_session

Use only when the entire persistent session is
explicitly complete or genuinely unrecoverable.

exit_session ends the whole session. No further user
turns will be prompted.

Do NOT use exit_session merely because the current
task is complete and the user may reasonably continue
working in the same session. Use final_answer for
normal turn completion.

Required parameter:

exit_summary

exit_summary must briefly explain why the session is
being terminated.

14. batch

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

Important rules:

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
            "USER REQUEST:\n"
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
)


# ==========================================
# 8. Agent loop
# ==========================================

# Session-scoped state is retained across user turns.
execution_result_records = session.execution_result_records
blocked_skipped_actions = session.blocked_skipped_actions

MAX_STEPS = 12


for step in session.iter_steps(
    MAX_STEPS
):

    logger.info(
        f"Step {step + 1} of {MAX_STEPS}"
    )

    print(
        f"\n--- Agent step {step + 1} ---"
    )

    try:

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
        )

        continue

    print(
        "\nAgent decision:"
    )

    print(
        decision
    )

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

        session.complete_turn()
        continue

    if (
        decision.action
        == "exit_session"
    ):

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
    )

else:

    logger.warning(
        "Agent session closed after the final user turn."
    )

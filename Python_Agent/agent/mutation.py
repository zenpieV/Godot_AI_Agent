"""
Mutation architecture: classification, result contract, and
verification status for Godot mutations.

This module is the single place that defines, on the Python side:

1. how an action is classified as a mutation (delegating to the
   registry's is_mutation flag, which is the authoritative
   classification),
2. the structured result contract every mutation tool result must
   satisfy (a dict with a boolean "success" key),
3. the verification status derived from a mutation result
   ("verified", "unverified", or "failed"), based on the
   "verified_*" fields the Godot bridge already reports,
4. the MutationRecord execution record built from a completed
   mutation, including the mutation target and undoability as
   reported by the Godot editor bridge.

This module performs NO execution and NO Godot I/O. It is a pure
classification/contract layer over results that already exist. It
does not change what any tool returns; it only makes mutation
results uniform and observable.

Undoability is not implemented here: mutations are already executed
on the Godot side as editor-native EditorUndoRedoManager actions,
and the bridge reports "undoable" in its results. This module only
carries that fact forward into structured records and telemetry.
"""

from dataclasses import dataclass

from agent.boundary import extract_mutation_target
from agent.registry import ACTION_REGISTRY


# ==========================================
# Verification status
# ==========================================

VERIFICATION_VERIFIED = "verified"
VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_FAILED = "failed"

VERIFICATION_STATUSES = (
    VERIFICATION_VERIFIED,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_FAILED,
)


def is_mutation_action(
    action_name,
) -> bool:
    """
    Classify an action by name using the registry's authoritative
    is_mutation flag. Unknown actions are not mutations.
    """

    spec = ACTION_REGISTRY.get(
        action_name
    )

    if spec is None:
        return False

    return spec.is_mutation


def validate_mutation_result(
    tool_result,
) -> tuple[bool, str]:
    """
    Enforce the structured mutation result contract.

    A mutation tool result must be a dict containing a boolean
    "success" key. Anything else is a contract violation: the
    mutation's outcome is unknown and must be recorded as a
    failure, never silently as a success.
    """

    if not isinstance(
        tool_result,
        dict,
    ):

        return (
            False,
            (
                "Mutation result contract "
                "violation: expected a dict "
                "result, got "
                + type(tool_result).__name__
                + "."
            ),
        )

    if "success" not in tool_result:

        return (
            False,
            (
                "Mutation result contract "
                "violation: result is missing "
                "the boolean 'success' key."
            ),
        )

    if not isinstance(
        tool_result["success"],
        bool,
    ):

        return (
            False,
            (
                "Mutation result contract "
                "violation: 'success' must be "
                "a boolean."
            ),
        )

    return (
        True,
        "",
    )


def classify_verification(
    tool_result,
) -> str:
    """
    Derive verification status from a contract-valid mutation
    result.

    Rules, in order:

    - success False                      -> "failed"
    - success True, any verified_* False -> "failed"
      (the bridge reported success but at least one
      verification claim did not hold)
    - success True, all present verified_*
      keys True (at least one present)    -> "verified"
    - success True, no verified_* keys    -> "unverified"

    "name_collision_detected" is informational and is NOT a
    verification claim (False is the good outcome there).
    """

    if not tool_result.get(
        "success"
    ):
        return VERIFICATION_FAILED

    verification_claims = [
        value
        for key, value in tool_result.items()
        if isinstance(key, str)
        and key.startswith("verified_")
    ]

    if not verification_claims:
        return VERIFICATION_UNVERIFIED

    if not all(
        claim is True
        for claim in verification_claims
    ):
        return VERIFICATION_FAILED

    return VERIFICATION_VERIFIED


@dataclass(frozen=True)
class MutationRecord:
    """
    Structured execution record for one mutation action.

    Built after execution from the existing tool result; never
    fabricates verification or undoability information.
    """

    action: str
    target: tuple
    success: bool
    verification: str
    undoable: object  # True / False / None (not reported)
    error: object     # error string or None
    turn_number: int
    step_number: int
    duration_ms: float
    contract_violation: str  # "" when the result satisfied the contract


def build_mutation_record(
    decision,
    tool_result,
    turn_number=0,
    step_number=0,
    duration_ms=0.0,
) -> MutationRecord:
    """
    Build a MutationRecord from a completed mutation execution.

    A contract violation forces success=False and
    verification="failed": an unparseable mutation result must
    never be observable as a confirmed success.
    """

    contract_ok, contract_reason = (
        validate_mutation_result(
            tool_result
        )
    )

    if not contract_ok:

        return MutationRecord(
            action=str(
                getattr(
                    decision,
                    "action",
                    "<unknown>",
                )
            ),
            target=extract_mutation_target(
                decision
            ),
            success=False,
            verification=VERIFICATION_FAILED,
            undoable=None,
            error=contract_reason,
            turn_number=turn_number,
            step_number=step_number,
            duration_ms=duration_ms,
            contract_violation=contract_reason,
        )

    success = tool_result["success"]

    error = None

    if not success:

        error = tool_result.get(
            "error"
        )

        if error is None:

            error = tool_result.get(
                "validation_error"
            )

    return MutationRecord(
        action=str(decision.action),
        target=extract_mutation_target(
            decision
        ),
        success=success,
        verification=classify_verification(
            tool_result
        ),
        undoable=tool_result.get(
            "undoable"
        ),
        error=error,
        turn_number=turn_number,
        step_number=step_number,
        duration_ms=duration_ms,
        contract_violation="",
    )

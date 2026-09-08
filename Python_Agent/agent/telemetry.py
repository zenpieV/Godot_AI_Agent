"""
Observability v1 telemetry model.

Collects structured telemetry for model calls, tool actions, batches,
context compaction, and session lifecycle. Designed to be extensible for
future JSONL logging, Godot UI, or cost analysis without building those
systems now.

All timing uses monotonic clocks. Token counts come from provider usage
metadata only - never estimated or fabricated.
"""

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


# ==========================================
# Token usage
# ==========================================


@dataclass
class TokenUsage:
    """Token usage from a single model call.

    When the provider exposes no usage metadata, all fields are None
    and available is False. Never fabricate these values.
    """

    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    available: bool = False


def _read_value(source, *names):
    if source is None:
        return None
    for name in names:
        if isinstance(source, dict) and name in source:
            return source[name]
        value = getattr(source, name, None)
        if value is not None:
            return value
    return None


def normalize_usage(metadata) -> TokenUsage:
    input_tokens = _read_value(
        metadata,
        "prompt_token_count",
        "prompt_tokens",
        "input_tokens",
    )
    output_tokens = _read_value(
        metadata,
        "candidates_token_count",
        "completion_tokens",
        "output_tokens",
        "eval_count",
    )
    total_tokens = _read_value(
        metadata,
        "total_token_count",
        "total_tokens",
    )

    values = (input_tokens, output_tokens, total_tokens)
    if not any(value is not None for value in values):
        return TokenUsage()

    return TokenUsage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        available=True,
    )


def safe_error_message(error: BaseException) -> str:
    message = str(error)[:200]
    for name in (
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENROUTER_API_KEY",
        "ZAI_API_KEY",
    ):
        secret = os.getenv(name)
        if secret:
            message = message.replace(secret, "[redacted]")
    return f"{type(error).__name__}: {message}"


# ==========================================
# Provider result envelope
# ==========================================


@dataclass
class ProviderResult:
    """Return type for provider adapters.

    Wraps the raw text response with normalized usage metadata so the
    agent loop can record telemetry without re-parsing provider SDK objects.
    """

    text: str
    usage: TokenUsage = field(default_factory=TokenUsage)


def provider_result_text(response) -> str:
    text = getattr(response, "text", None)
    if text is not None:
        return text
    message = getattr(response, "message", None)
    content = getattr(message, "content", None)
    if content is not None:
        return content
    choices = getattr(response, "choices", None)
    if choices:
        return choices[0].message.content
    return str(response)


# ==========================================
# Event telemetry records
# ==========================================


@dataclass
class ModelCallTelemetry:
    """Telemetry for a single model/provider call."""

    call_id: str
    session_id: str
    turn_number: int
    step_number: int
    provider: str
    model: str
    duration_ms: float
    usage: TokenUsage
    success: bool
    started_at: float = 0.0
    error: Optional[str] = None


@dataclass
class ToolActionTelemetry:
    """Telemetry for a single tool/action execution."""

    session_id: str
    turn_number: int
    step_number: int
    action: str
    success: bool
    duration_ms: float
    model_call_id: Optional[str] = None


@dataclass
class BatchTelemetry:
    """Telemetry for a batch execution."""

    session_id: str
    turn_number: int
    step_number: int
    batch_size: int
    succeeded_count: int
    failed_count: int
    stopped_early: bool
    stopped_at_index: Optional[int]
    duration_ms: float
    success: bool


@dataclass
class CompactionTelemetry:
    """Telemetry for a context compaction event."""

    session_id: str
    turn_number: int
    step_number: int
    original_length: int
    summary_length: int
    action: str
    duration_ms: float = 0.0


# ==========================================
# Session summary
# ==========================================


@dataclass
class SessionSummary:
    """Aggregated session-level summary produced at termination."""

    session_id: str
    turns_completed: int
    agent_steps: int
    model_calls: int
    total_input_tokens: Optional[int]
    total_output_tokens: Optional[int]
    total_tokens: Optional[int]
    total_tokens_complete: bool
    usage_unavailable_count: int
    tool_action_count: int
    successful_action_count: int
    failed_action_count: int
    batch_count: int
    total_batched_actions: int
    compaction_count: int
    duration_ms: float
    termination_reason: str


def new_call_id() -> str:
    return str(uuid.uuid4())[:8]


# ==========================================
# Session observability collector
# ==========================================


class SessionObservability:
    """Collects telemetry events for one agent session."""

    def __init__(
        self,
        session_id: str,
    ):
        self.session_id = session_id
        self.model_calls: list[ModelCallTelemetry] = []
        self.tool_actions: list[ToolActionTelemetry] = []
        self.batches: list[BatchTelemetry] = []
        self.compactions: list[CompactionTelemetry] = []
        self._start_time = time.monotonic()

    def record_model_call(
        self,
        call_id: str,
        turn_number: int,
        step_number: int,
        provider: str,
        model: str,
        duration_ms: float,
        usage: TokenUsage,
        success: bool,
        started_at: float = 0.0,
        error: Optional[str] = None,
    ) -> None:
        self.model_calls.append(
            ModelCallTelemetry(
                call_id=call_id,
                session_id=self.session_id,
                turn_number=turn_number,
                step_number=step_number,
                provider=provider,
                model=model,
                duration_ms=duration_ms,
                usage=usage,
                success=success,
                started_at=started_at,
                error=error,
            )
        )

    def record_tool_action(
        self,
        turn_number: int,
        step_number: int,
        action: str,
        success: bool,
        duration_ms: float,
        model_call_id: Optional[str] = None,
    ) -> None:
        self.tool_actions.append(
            ToolActionTelemetry(
                session_id=self.session_id,
                turn_number=turn_number,
                step_number=step_number,
                action=action,
                success=success,
                duration_ms=duration_ms,
                model_call_id=model_call_id,
            )
        )

    def record_batch(
        self,
        turn_number: int,
        step_number: int,
        batch_size: int,
        succeeded_count: int,
        failed_count: int,
        stopped_early: bool,
        stopped_at_index: Optional[int],
        duration_ms: float,
        success: bool,
    ) -> None:
        self.batches.append(
            BatchTelemetry(
                session_id=self.session_id,
                turn_number=turn_number,
                step_number=step_number,
                batch_size=batch_size,
                succeeded_count=succeeded_count,
                failed_count=failed_count,
                stopped_early=stopped_early,
                stopped_at_index=stopped_at_index,
                duration_ms=duration_ms,
                success=success,
            )
        )

    def record_compaction(
        self,
        turn_number: int,
        step_number: int,
        original_length: int,
        summary_length: int,
        action: str,
        duration_ms: float = 0.0,
    ) -> None:
        self.compactions.append(
            CompactionTelemetry(
                session_id=self.session_id,
                turn_number=turn_number,
                step_number=step_number,
                original_length=original_length,
                summary_length=summary_length,
                action=action,
                duration_ms=duration_ms,
            )
        )

    def get_summary(
        self,
        turns_completed: int,
        termination_reason: str,
    ) -> SessionSummary:
        total_input = 0
        total_output = 0
        total = 0
        unavailable = 0
        complete_usage = True
        input_known = False
        output_known = False
        total_known = False

        for call in self.model_calls:
            if not call.usage.available:
                unavailable += 1
                complete_usage = False
                continue
            if call.usage.input_tokens is None:
                complete_usage = False
            else:
                input_known = True
                total_input += call.usage.input_tokens
            if call.usage.output_tokens is None:
                complete_usage = False
            else:
                output_known = True
                total_output += call.usage.output_tokens
            if call.usage.total_tokens is None:
                complete_usage = False
            else:
                total_known = True
                total += call.usage.total_tokens

        successful_actions = sum(
            1 for a in self.tool_actions if a.success
        )
        failed_actions = sum(
            1 for a in self.tool_actions if not a.success
        )
        total_batched = sum(
            b.batch_size for b in self.batches
        )

        duration_ms = (
            time.monotonic() - self._start_time
        ) * 1000

        return SessionSummary(
            session_id=self.session_id,
            turns_completed=turns_completed,
            agent_steps=len({
                (call.turn_number, call.step_number)
                for call in self.model_calls
            }),
            model_calls=len(self.model_calls),
            total_input_tokens=(
                total_input if input_known else None
            ),
            total_output_tokens=(
                total_output if output_known else None
            ),
            total_tokens=(
                total if total_known else None
            ),
            total_tokens_complete=bool(self.model_calls) and complete_usage,
            usage_unavailable_count=unavailable,
            tool_action_count=len(self.tool_actions),
            successful_action_count=successful_actions,
            failed_action_count=failed_actions,
            batch_count=len(self.batches),
            total_batched_actions=total_batched,
            compaction_count=len(self.compactions),
            duration_ms=duration_ms,
            termination_reason=termination_reason,
        )

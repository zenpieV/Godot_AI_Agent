@tool
extends RefCounted

class_name AIAgentAgentStateStore


# ==========================================
# Agent state store
# ==========================================
# In-plugin state for the agent observability UI. Python pushes
# small flat events to POST /agent_event; this store applies
# them, keeps bounded histories, and notifies the panel via
# signals. Interpretation lives HERE, transport lives in
# Python's UiReporter, so the two sides evolve independently:
# unknown event types are stored as generic activity rows and
# unknown fields are ignored, never rejected.
#
# Deliberate design rules:
# - Read-only from the UI's perspective: the panel renders
#   snapshots; only apply_event() mutates state.
# - Every history is a bounded ring; a long session can never
#   grow editor memory without limit.
# - Timestamps: events carry Python's unix "ts" when provided;
#   display ordering uses arrival order, and ms-timestamps for
#   "now" use Time.get_ticks_msec() (monotonic within the
#   editor process).


signal events_updated

signal status_changed

signal ledger_updated

signal chat_updated

signal metrics_updated


const MAX_EVENTS := 500

const MAX_LEDGER := 200

const MAX_CHAT_TURNS := 50

const MAX_METRICS := 200

const MAX_THINKING_CHARS := 300


# Status values (mirrored by the panel's color/icon mapping).

const STATUS_READY := "ready"

const STATUS_THINKING := "thinking"

const STATUS_EXECUTING_TOOL := "executing_tool"

const STATUS_OFFLINE_RUN := "offline_run"

const STATUS_WAITING_APPROVAL := "waiting_approval"

const STATUS_COMPLETED := "completed"

const STATUS_NEEDS_ATTENTION := "needs_attention"

const STATUS_ERROR := "error"

const STATUS_SESSION_ENDED := "session_ended"


var status: String = STATUS_READY

var status_detail: String = ""

var session_id: String = ""

var model_label: String = ""

var turn_number: int = 0

var step_number: int = 0

var request_preview: String = ""

var session_started_ms: int = 0

var turn_started_ms: int = 0

var last_tool_action: String = ""

# Token and call accounting (sums only ever grow within a
# session; reset on session_started).

var model_call_count: int = 0

var total_prompt_tokens: int = 0

var total_output_tokens: int = 0

var usage_unavailable_count: int = 0

var last_prompt_tokens: int = -1

var last_output_tokens: int = -1

var last_duration_ms: float = -1.0

# Bounded histories.

var events: Array = []

var ledger: Array = []

var chat_turns: Array = []

var metrics: Array = []

# ---- Control channel (phase: chat input box) ----
#
# The panel's input box queues the next user request here;
# the agent (running in bridge input mode) consumes it via
# GET /agent_input, which is also the agent-alive heartbeat
# the panel's connection dot renders.

# FIFO queue (max 5): requests submitted while the
# agent is busy are served in order instead of the
# newest displacing everything else.

var pending_requests: Array = []

var selected_provider: String = ""

var selected_model: String = ""

var available_models: Array = []

var last_input_poll_ms: int = 0

# The port the plugin's bridge listens on; the panel posts
# its input/model selections to the same bridge. Set by the
# plugin so panel and server can never drift apart.

var bridge_port: int = 8081

# Context meter: approximate conversation size (the last
# model call's prompt tokens include the whole
# conversation) against the provider's configured limit.
var context_limit: int = 0
var context_used_tokens: int = 0

# New Session respawn flow (see the panel).
var respawn_pending: bool = false
	# Approval gate: one pending request and its decision
	# (-1 none, 0 denied, 1 approved).
var approval_id: String = ""
var approval_action: String = ""
var approval_decision: int = -1

# Start Session flow: the panel's status button spawns the
# agent process; between the click and the agent's
# session_started event the button shows STARTING... The
# panel clears the flag on a spawn failure and enforces a
# retry timeout itself.

var session_starting: bool = false

var session_starting_ms: int = 0


func _init() -> void:

	session_started_ms = (
		Time.get_ticks_msec()
	)

	turn_started_ms = (
		session_started_ms
	)


# ==========================================
# Bridge entry points
# ==========================================


func apply_event_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("event"):

		return {
			"success": false,
			"error": (
				"agent_event requires an "
				+ "'event' type field."
			)
		}

	if typeof(data["event"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"agent_event 'event' field "
				+ "must be a string."
			)
		}

	if str(data["event"]).strip_edges().is_empty():

		return {
			"success": false,
			"error": (
				"agent_event 'event' field "
				+ "must not be empty."
			)
		}

	apply_event(data)

	return {
		"success": true,
		"action": "agent_event",
		"event": str(data["event"]),
	}


func apply_event(
	event: Dictionary
) -> void:

	var event_type := str(
		event.get("event", "event")
	)

	match event_type:

		"session_started":
			# The MUTATION LEDGER deliberately survives
			# session_started: it is a project-level
			# audit trail, and each agent CLI process
			# emits session_started at startup - wiping
			# here would hide every mutation from
			# earlier runs. Timeline, metrics and chat
			# reset; the ledger only ever rolls over at
			# MAX_LEDGER.
			_reset()
			session_starting = false
			session_id = str(
				event.get("session_id", "")
			)
			model_label = str(
				event.get("model", "")
			)

			context_limit = int(
				event.get("context_limit", 0)
			)
			if event.has("available_models") and (
				event["available_models"] is Array
			):
				available_models = (
					event["available_models"].duplicate()
				)
			_set_status(
				STATUS_READY,
				"Session %s ready." % session_id
			)

		"model_selected":
			# The panel's model selector: applies to the
			# NEXT turn (the agent applies it when it
			# consumes its next input poll).
			if event.has("provider"):
				selected_provider = str(
					event["provider"]
				)
			if event.has("model") and str(
				event["model"]
			) != "":
				selected_model = str(event["model"])
				model_label = selected_model
			_add_event(
				"event",
				"Model selected: %s" % model_label,
				selected_provider,
				turn_number
			)

		"turn_started":
			turn_number = int(
				event.get("turn", turn_number)
			)
			step_number = 0
			request_preview = str(
				event.get("request_preview", "")
			)
			turn_started_ms = Time.get_ticks_msec()
			_set_status(
				STATUS_READY,
				""
			)
			_append_chat_turn(
				turn_number,
				request_preview,
				str(event.get("mode", "act"))
			)
			_add_event(
				"turn",
				"Turn %d started%s" % [
					turn_number,
					" (PLAN)" if str(
						event.get("mode", "")
					) == "plan" else "",
				],
				request_preview,
				turn_number
			)

		"request_sent":
			step_number = int(
				event.get("step", step_number)
			)
			if event.has("model") and event["model"] != null:
				model_label = str(event["model"])
			_set_status(STATUS_THINKING, "")
			_add_event(
				"step",
				"Step %d - asking model" % step_number,
				model_label,
				turn_number
			)

		"model_response":
			# Metrics and status only: the decision
			# summary row comes from the "thinking"
			# event, which carries the model's reason.
			_apply_usage(event)
			_set_status(
				STATUS_THINKING,
				""
			)

		"thinking":
			_append_chat_thinking(
				str(event.get("reason", ""))
			)
			_add_event(
				"reasoning",
				str(event.get("reason", "")),
				"%s - %s" % [
					_format_tokens_last(),
					str(event.get("action", "")),
				],
				turn_number
			)

		"tool_started":
			last_tool_action = str(
				event.get("action", "")
			)
			if last_tool_action == "run_scene_offline":
				_set_status(STATUS_OFFLINE_RUN, last_tool_action)
			else:
				_set_status(
					STATUS_EXECUTING_TOOL,
					last_tool_action
				)
			_add_event(
				"tool",
				"%s %s" % [
					last_tool_action,
					_batch_suffix(event),
				],
				"",
				turn_number
			)

		"tool_finished":
			var succeeded: bool = bool(
				event.get("success", false)
			)
			var summary := "%s %s" % [
				str(event.get("action", "?")),
				"OK" if succeeded else "FAILED",
			]
			if event.has("verification"):
				summary += " - %s" % str(
					event["verification"]
				)
			if event.has("duration_ms") and event["duration_ms"] != null:
				summary += " - %s ms" % str(
					event["duration_ms"]
				)
			_add_event(
				"tool_result",
				summary,
				str(event.get("detail", "")),
				turn_number
			)
			if event.get("is_mutation", false):
				_append_ledger(event)

		"batch_started":
			_set_status(
				STATUS_EXECUTING_TOOL,
				"batch"
			)
			_add_event(
				"batch",
				"Batch of %d action(s) started" % int(
					event.get("batch_size", 0)
				),
				"",
				turn_number
			)

		"batch_finished":
			_add_event(
				"batch",
				"Batch finished (%s)" % (
					"OK" if bool(
						event.get("success", false)
					) else "FAILED"
				),
				"",
				turn_number
			)

		"compaction":
			_add_event(
				"compaction",
				"Context compacted: %s -> %s chars" % [
					str(event.get("original_chars", "?")),
					str(event.get("summary_chars", "?")),
				],
				str(event.get("action", "")),
				turn_number
			)

		"blocked_action":
			_set_status(
				STATUS_NEEDS_ATTENTION,
				"blocked action"
			)
			_add_event(
				"blocked",
				"Blocked: %s" % str(
					event.get("action", "?")
				),
				str(event.get("reason", "")),
				turn_number
			)

		"validation_rejected":
			_set_status(
				STATUS_NEEDS_ATTENTION,
				"invalid decision"
			)
			_add_event(
				"validation",
				"Rejected: %s" % str(
					event.get("action", "?")
				),
				str(event.get("error", "")),
				turn_number
			)

		"attention":
			_set_status(
				STATUS_NEEDS_ATTENTION,
				str(event.get("kind", ""))
			)
			_add_event(
				"attention",
				str(event.get("kind", "attention")),
				str(event.get("detail", "")),
				turn_number
			)

		"error":
			_set_status(
				STATUS_ERROR,
				str(event.get("context", ""))
			)
			_add_event(
				"error",
				"Error: %s" % str(
					event.get("context", "?")
				),
				str(event.get("error", "")),
				turn_number
			)

		"max_steps_reached":
			_set_status(
				STATUS_NEEDS_ATTENTION,
				"max steps"
			)
			_add_event(
				"attention",
				"Turn %d reached max steps" % int(
					event.get("turn", 0)
				),
				"",
				turn_number
			)

		"approval_requested":
			approval_id = str(event.get("approval_id", ""))
			approval_action = str(event.get("action", ""))
			approval_decision = -1
			_set_status(STATUS_WAITING_APPROVAL, approval_action)
			_add_event(
				"attention",
				"Approval requested: %s" % approval_action,
				approval_action,
				turn_number
			)

		"approval_decision":
			approval_id = str(event.get("approval_decision_id", approval_id))
			approval_decision = (
				1 if bool(event.get("approved", false))
				else 0
			)
			_set_status(
				STATUS_EXECUTING_TOOL if approval_decision == 1
				else STATUS_NEEDS_ATTENTION,
				approval_action
			)
			_add_event(
				"event",
				"Approval %s for %s" % [
					"granted" if approval_decision == 1 else "denied",
					approval_action,
				],
				"",
				turn_number
			)

		"turn_completed":
			_complete_chat_turn(
				str(event.get("final_answer", ""))
			)
			_set_status(STATUS_COMPLETED, "")
			_add_event(
				"answer",
				"Turn %d completed" % int(
					event.get("turn", 0)
				),
				str(event.get("final_answer", "")),
				turn_number
			)

		"session_ended":
			_set_status(
				STATUS_SESSION_ENDED,
				str(event.get("reason", ""))
			)
			_add_event(
				"session",
				"Session ended (%s)" % str(
					event.get("reason", "")
				),
				"",
				turn_number
			)

		_:
			# Unknown event types are tolerated as
			# generic rows so the reporter can evolve
			# ahead of the plugin.
			_add_event(
				"event",
				event_type,
				"",
				turn_number
			)

	events_updated.emit()


func mark_session_starting() -> void:

	session_starting = true

	session_starting_ms = Time.get_ticks_msec()

	status_changed.emit()


func mark_session_start_failed() -> void:

	session_starting = false

	_set_status(
		STATUS_NEEDS_ATTENTION,
		"could not launch the agent process"
	)


func is_session_running() -> bool:

	return (
		session_id != ""
		and status != STATUS_SESSION_ENDED
	)


func snapshot() -> Dictionary:

	return {
		"success": true,
		"status": status,
		"status_detail": status_detail,
		"session_id": session_id,
		"model": model_label,
		"turn": turn_number,
		"step": step_number,
		"busy": is_busy(),
		"pending_count": pending_requests.size(),
		"selected_provider": selected_provider,
		"selected_model": selected_model,
		"available_models": available_models.duplicate(),
		"agent_connected": is_agent_connected(),
		"model_call_count": model_call_count,
		"total_prompt_tokens": total_prompt_tokens,
		"total_output_tokens": total_output_tokens,
		"usage_unavailable_count": usage_unavailable_count,
		"last_prompt_tokens": last_prompt_tokens,
		"last_output_tokens": last_output_tokens,
		"last_duration_ms": last_duration_ms,
		"event_count": events.size(),
		"ledger_count": ledger.size(),
		"chat_turn_count": chat_turns.size(),
		"metrics_count": metrics.size(),
		"events": events.slice(
			maxi(0, events.size() - 50)
		),
		"ledger": ledger.duplicate(),
		"chat_turns": chat_turns.duplicate(),
		"metrics": metrics.duplicate(),
	}


# ==========================================
# Control channel
# ==========================================


func submit_input_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("text"):

		return {
			"success": false,
			"error": (
				"agent_input requires text."
			)
		}

	if typeof(data["text"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"agent_input text must be a "
				+ "string."
			)
		}

	var text := str(data["text"]).strip_edges()

	if text.is_empty():

		return {
			"success": false,
			"error": (
				"agent_input text must not be "
				+ "empty."
			)
		}

	var mode := str(data.get("mode", "act"))
	if mode != "plan":
		mode = "act"

	var was_queued: bool = pending_requests.size() >= 1

	# FIFO: append at the back; the agent consumes the
	# oldest first. Beyond 5 pending requests the
	# submission is refused rather than queued.
	if pending_requests.size() >= 5:
		return {
			"success": false,
			"error": (
				"agent_input queue is full (5 pending "
				+ "requests); the agent is busy."
			)
		}

	pending_requests.append({
		"text": text.substr(0, 2000),
		"mode": mode,
	})

	return {
		"success": true,
		"action": "agent_input",
		"queued": was_queued,
	}


func consume_input_snapshot() -> Dictionary:

	# GET /agent_input: consume-on-read of the pending
	# request, plus the current model selection. Doubles
	# as the agent-alive heartbeat.

	last_input_poll_ms = Time.get_ticks_msec()

	var has_pending: bool = not pending_requests.is_empty()
	var front: Dictionary = (
		pending_requests.pop_front()
	) if has_pending else {}

	var snapshot := {
		"success": true,
		"pending": has_pending,
		"text": str(front.get("text", "")),
		"mode": str(front.get("mode", "act")),
		"selected_provider": selected_provider,
		"selected_model": selected_model,
	}

	return snapshot


func submit_approval_from_request(data: Dictionary) -> Dictionary:

	if not data.has("approved"):
		return {
			"success": false,
			"error": "agent_approval requires approved.",
	}

	if approval_id.is_empty():
		return {
			"success": false,
			"error": "no approval is currently pending.",
	}

	approval_decision = 1 if bool(data["approved"]) else 0

	return {
		"success": true,
		"action": "agent_approval",
		"recorded": true,
}


func consume_approval_snapshot() -> Dictionary:

	last_input_poll_ms = Time.get_ticks_msec()

	if approval_decision == -1:
		return {
			"success": true,
			"pending": false,
			"approved": false,
	}

	var snapshot := {
		"success": true,
		"pending": true,
		"approved": approval_decision == 1,
	}

	# Decision consumed; the agent proceeds (approved) or
	# reports the denial (denied).
	approval_decision = -1
	return snapshot

func is_agent_connected() -> bool:

	# Bridge input mode polls regularly; CLI stdin mode
	# never polls (last_input_poll_ms stays 0 = unknown,
	# rendered as such rather than as offline).

	if last_input_poll_ms == 0:
		return false

	# While a turn is in flight the agent legitimately
	# stops polling (it is busy executing) - busy means
	# alive, never stale.

	if is_busy():
		return true

	return (
		Time.get_ticks_msec() - last_input_poll_ms
		< 2500
	)


func is_busy() -> bool:

	return (
		status == STATUS_THINKING
		or status == STATUS_EXECUTING_TOOL
		or status == STATUS_OFFLINE_RUN
	)


func turn_elapsed_seconds() -> float:

	var elapsed_ms := Time.get_ticks_msec() - turn_started_ms

	return maxf(0.0, elapsed_ms / 1000.0)


# ==========================================
# Internals
# ==========================================


func _reset() -> void:

	status = STATUS_READY

	status_detail = ""

	session_id = ""

	model_label = ""

	turn_number = 0

	step_number = 0

	request_preview = ""

	session_started_ms = Time.get_ticks_msec()

	turn_started_ms = session_started_ms

	last_tool_action = ""

	model_call_count = 0

	total_prompt_tokens = 0

	total_output_tokens = 0

	usage_unavailable_count = 0

	last_prompt_tokens = -1

	last_output_tokens = -1

	last_duration_ms = -1.0

	events.clear()

	pending_requests.clear()

	chat_turns.clear()

	metrics.clear()

	chat_updated.emit()

	metrics_updated.emit()


func _set_status(
	new_status: String,
	detail: String
) -> void:

	status = new_status

	status_detail = detail

	status_changed.emit()


func _add_event(
	kind: String,
	summary: String,
	detail: String,
	turn: int
) -> void:

	events.append(
		{
			"kind": kind,
			"summary": summary,
			"detail": detail,
			"turn": turn,
			"ts_ms": Time.get_ticks_msec(),
		}
	)

	if events.size() > MAX_EVENTS:
		events.pop_front()


func _apply_usage(
	event: Dictionary
) -> void:

	model_call_count += 1

	if event.has("prompt_tokens") and event["prompt_tokens"] != null:
		context_used_tokens = int(event["prompt_tokens"])

	var prompt_tokens: int = -1

	var output_tokens: int = -1

	if event.has("prompt_tokens") and event["prompt_tokens"] != null:
		prompt_tokens = int(event["prompt_tokens"])

	if event.has("output_tokens") and event["output_tokens"] != null:
		output_tokens = int(event["output_tokens"])

	if prompt_tokens >= 0:
		last_prompt_tokens = prompt_tokens
		total_prompt_tokens += prompt_tokens
	else:
		last_prompt_tokens = -1

	if output_tokens >= 0:
		last_output_tokens = output_tokens
		total_output_tokens += output_tokens
	else:
		last_output_tokens = -1

	if (
		prompt_tokens < 0
		and output_tokens < 0
	):
		usage_unavailable_count += 1

	if event.has("duration_ms") and event["duration_ms"] != null:
		last_duration_ms = float(event["duration_ms"])

	metrics.append(
		{
			"call": model_call_count,
			"turn": int(event.get("turn", 0)),
			"step": int(event.get("step", 0)),
			"model": str(event.get("model", "")),
			"prompt_tokens": prompt_tokens,
			"output_tokens": output_tokens,
			"duration_ms": last_duration_ms,
		}
	)

	if metrics.size() > MAX_METRICS:
		metrics.pop_front()

	metrics_updated.emit()


func _append_ledger(
	event: Dictionary
) -> void:

	ledger.append(
		{
			"ts_ms": Time.get_ticks_msec(),
			"turn": int(event.get("turn", 0)),
			"action": str(event.get("action", "?")),
			"target": str(event.get("target", "")),
			"target_path": str(
				event.get("target_path", "")
			),
			"verification": str(
				event.get("verification", "unverified")
			),
			"undoable": bool(
				event.get("undoable", false)
			),
			"success": bool(
				event.get("success", false)
			),
		}
	)

	if ledger.size() > MAX_LEDGER:
		ledger.pop_front()

	ledger_updated.emit()


func _append_chat_turn(
	turn: int,
	request: String,
	mode: String = "act"
) -> void:

	chat_turns.append(
		{
			"ts_ms": Time.get_ticks_msec(),
			"turn": turn,
			"request": request,
			"mode": mode if mode != "" else "act",
			"thinking": "",
			"final_answer": "",
			"completed": false,
		}
	)

	if chat_turns.size() > MAX_CHAT_TURNS:
		chat_turns.pop_front()

	chat_updated.emit()


func _append_chat_thinking(
	reason: String
) -> void:

	if chat_turns.is_empty():
		return

	var entry: Dictionary = chat_turns.back()

	# Single in-place line: the latest reason REPLACES the
	# previous one (chat-LLM style). The field is cleared
	# entirely when the final answer arrives.

	entry["thinking"] = reason.substr(
		0, MAX_THINKING_CHARS
	)

	chat_updated.emit()


func _complete_chat_turn(
	final_answer: String
) -> void:

	if chat_turns.is_empty():
		return

	var entry: Dictionary = chat_turns.back()

	entry["final_answer"] = final_answer

	entry["thinking"] = ""

	entry["completed"] = true

	chat_updated.emit()


func _format_tokens_last() -> String:

	if last_prompt_tokens < 0 and last_output_tokens < 0:
		return "tokens unavailable"

	return "%s in / %s out" % [
		str(last_prompt_tokens),
		str(last_output_tokens),
	]


func _batch_suffix(
	event: Dictionary
) -> String:

	if not event.has("batch_index"):
		return ""

	return "(%s/%s)" % [
		str(event.get("batch_index", "?")),
		str(event.get("batch_size", "?")),
	]

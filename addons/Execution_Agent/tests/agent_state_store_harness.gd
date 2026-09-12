extends SceneTree

const AIAgentStateStoreScript = preload(
	"res://addons/Execution_Agent/ui/ai_agent_state_store.gd"
)

const AIAgentRouterScript = preload(
	"res://addons/Execution_Agent/bridge/ai_agent_router.gd"
)


var store


func _apply(event: Dictionary) -> void:
	store.apply_event(event)


func _run_store_cases() -> void:
	# 1. Initial state is READY with empty histories.
	assert(store.status == "ready")
	assert(store.events.is_empty())
	assert(store.model_call_count == 0)

	# 2. session_started resets everything and records the
	# model label.
	_apply({"event": "session_started",
		"session_id": "abc123", "model": "gemini:gemini-3.5-flash-lite"})
	assert(store.status == "ready")
	assert(store.session_id == "abc123")
	assert(store.model_label == "gemini:gemini-3.5-flash-lite")
	assert(store.turn_number == 0)

	# 3. Turn lifecycle: ready -> thinking -> executing ->
	# completed, with tokens and metrics accumulated.
	_apply({"event": "turn_started", "turn": 1,
		"request_preview": "Rename the probe script.",
		"mode": "plan"})
	assert(store.turn_number == 1)
	assert(store.request_preview == "Rename the probe script.")
	assert(store.chat_turns.size() == 1)
	assert(store.chat_turns[0]["mode"] == "plan")

	_apply({"event": "request_sent", "turn": 1, "step": 1,
		"model": "gemini:gemini-3.5-flash-lite"})
	assert(store.status == "thinking")
	assert(store.step_number == 1)

	_apply({"event": "model_response", "turn": 1, "step": 1,
		"model": "gemini-3.5-flash-lite",
		"prompt_tokens": 1000, "output_tokens": 50,
		"duration_ms": 830.5})
	assert(store.model_call_count == 1)
	assert(store.total_prompt_tokens == 1000)
	assert(store.total_output_tokens == 50)
	assert(store.last_prompt_tokens == 1000)
	assert(store.metrics.size() == 1)

	# The thinking event carries the model's reason into
	# both the activity timeline and the chat transcript.
	# The transcript keeps ONE in-place line: a new reason
	# REPLACES the previous one.
	_apply({"event": "thinking", "turn": 1, "step": 1,
		"action": "create_node",
		"reason": "Creating the requested node.",
		"prompt_tokens": 1000, "output_tokens": 50})
	var kinds_seen := {}
	for e in store.events:
		kinds_seen[str(e["kind"])] = true
	assert(kinds_seen.has("reasoning"))
	assert(store.chat_turns.size() == 1)
	assert(store.chat_turns[0]["request"] == "Rename the probe script.")
	assert(store.chat_turns[0]["thinking"] == "Creating the requested node.")
	assert(store.chat_turns[0]["completed"] == false)

	_apply({"event": "thinking", "turn": 1, "step": 2,
		"action": "validate_node_type",
		"reason": "Checking the node type first.",
		"prompt_tokens": 1000, "output_tokens": 40})
	assert(store.chat_turns[0]["thinking"] == "Checking the node type first.")

	_apply({"event": "tool_started", "turn": 1, "step": 1,
		"action": "create_node", "batch_index": 2, "batch_size": 3})
	assert(store.status == "executing_tool")

	_apply({"event": "tool_finished", "turn": 1, "step": 1,
		"action": "create_node", "success": true,
		"duration_ms": 31.0, "is_mutation": true,
		"batch_index": 2, "batch_size": 3,
		"verification": "verified", "undoable": true,
		"target": "Root/Alpha"})
	assert(store.ledger.size() == 1)
	assert(store.ledger[0]["verification"] == "verified")
	assert(store.ledger[0]["target"] == "Root/Alpha")

	_apply({"event": "turn_completed", "turn": 1,
		"final_answer": "Created successfully."})
	assert(store.status == "completed")
	assert(store.chat_turns.size() == 1)
	assert(store.chat_turns[0]["final_answer"] == "Created successfully.")
	assert(store.chat_turns[0]["completed"] == true)
	assert(store.chat_turns[0]["mode"] == "plan")
	# The thinking line is removed once the answer arrives.
	assert(store.chat_turns[0]["thinking"] == "")

	# 4. run_scene_offline gets its own status while running.
	_apply({"event": "turn_started", "turn": 2, "request_preview": "Run it."})
	_apply({"event": "tool_started", "turn": 2, "step": 1,
		"action": "run_scene_offline"})
	assert(store.status == "offline_run")
	_apply({"event": "tool_finished", "turn": 2, "step": 1,
		"action": "run_scene_offline", "success": true,
		"duration_ms": 1200.0, "is_mutation": false})
	assert(store.ledger.size() == 1)

	# 5. Attention and error states.
	_apply({"event": "blocked_action", "turn": 2, "step": 2,
		"action": "rename_node", "reason": "blocked resume"})
	assert(store.status == "needs_attention")
	_apply({"event": "error", "context": "model_call",
		"error": "503 transient"})
	assert(store.status == "error")

	# 6. session_ended freezes the status; histories remain.
	_apply({"event": "session_ended", "reason": "exit_session",
		"turns_completed": 2})
	assert(store.status == "session_ended")
	assert(store.events.size() > 0)

	# 7. The mutation LEDGER survives the next session_started
	# (it is a project-level audit trail; each agent CLI
	# process emits session_started at startup).
	_apply({"event": "session_started", "session_id": "abc456",
		"model": "gemini-3.5-flash-lite"})
	assert(store.status == "ready")
	assert(store.ledger.size() == 1)
	assert(store.events.is_empty())
	assert(store.chat_turns.is_empty())
	assert(store.model_call_count == 0)

	print("state store lifecycle cases passed")


func _run_bounds_and_tolerance_cases() -> void:
	# 1. Unknown event types are tolerated as generic rows.
	_apply({"event": "some_future_event", "x": 1})
	var kinds := {}
	for e in store.events:
		kinds[str(e["kind"])] = true
	assert(kinds.has("event"))

	# 2. Usage-unavailable events count but never fabricate.
	_apply({"event": "session_started"})
	var events_before: int = store.model_call_count
	_apply({"event": "model_response", "turn": 1, "step": 1,
		"model": "m"})
	assert(store.model_call_count == events_before + 1)
	assert(store.usage_unavailable_count == 1)
	assert(store.last_prompt_tokens == -1)

	# 3. Ring buffers are bounded.
	_apply({"event": "session_started"})
	var index := 0
	while index < 600:
		_apply({"event": "tool_started", "turn": 1,
			"step": 1, "action": "probe_%d" % index})
		index += 1
	assert(store.events.size() == store.MAX_EVENTS)

	# 4. Snapshot shape (the /agent_state payload).
	var snap: Dictionary = store.snapshot()
	assert(snap["success"] == true)
	assert(snap.has("status"))
	assert(snap.has("total_prompt_tokens"))
	assert(snap.has("chat_turns"))
	assert(snap["events"].size() == 50)

	print("state store bounds/tolerance cases passed")


func _run_router_cases() -> void:
	# The router exposes the UI routes without any model-facing
	# registry change. Non-store deps are null; only the two UI
	# routes are exercised here.
	var router = AIAgentRouterScript.new(
		null, null, null, null, null, null, null, store
	)

	var ok: Dictionary = router.route_request(
		"POST",
		"/agent_event",
		JSON.stringify(
			{"event": "session_started", "session_id": "rt1"}
		)
	)
	assert(ok["success"] == true)
	assert(store.session_id == "rt1")

	var bad: Dictionary = router.route_request(
		"POST",
		"/agent_event",
		JSON.stringify({"no_event_field": true})
	)
	assert(bad["success"] == false)
	assert(bad["error"].contains("'event'"))

	var bad_type: Dictionary = router.route_request(
		"POST",
		"/agent_event",
		JSON.stringify({"event": 5})
	)
	assert(bad_type["success"] == false)

	var snap: Dictionary = router.route_request(
		"GET",
		"/agent_state",
		""
	)
	assert(snap["success"] == true)
	assert(snap["session_id"] == "rt1")

	print("agent UI router cases passed")


func _run_control_channel_cases() -> void:
	# 1. Submission validation.
	var no_text = store.submit_input_from_request({})
	assert(no_text["success"] == false)

	var empty_text = store.submit_input_from_request(
		{"text": "   "}
	)
	assert(empty_text["success"] == false)

	# 2. Submit -> consume-on-read, exactly once, with the
	# heartbeat recorded. The mode travels with the text.
	var first = store.submit_input_from_request(
		{"text": "  Count the nodes.  ", "mode": "act"}
	)
	assert(first["success"] == true)
	assert(first["queued"] == false)

	var consumed = store.consume_input_snapshot()
	assert(consumed["pending"] == true)
	assert(consumed["text"] == "Count the nodes.")
	assert(consumed["mode"] == "act")
	assert(consumed["selected_model"] == "")

	var second = store.consume_input_snapshot()
	assert(second["pending"] == false)
	assert(second["text"] == "")
	assert(store.is_agent_connected() == true)

	# 3. FIFO: requests are served oldest-first, each
	# carrying its own mode. Absent mode defaults to act.
	store.submit_input_from_request(
		{"text": "one", "mode": "act"}
	)
	var displaced = store.submit_input_from_request(
		{"text": "two", "mode": "plan"}
	)
	assert(displaced["queued"] == true)
	store.submit_input_from_request({"text": "three"})

	var latest = store.consume_input_snapshot()
	assert(latest["text"] == "one")
	assert(latest["mode"] == "act")
	var latest2 = store.consume_input_snapshot()
	assert(latest2["text"] == "two")
	assert(latest2["mode"] == "plan")
	var latest3 = store.consume_input_snapshot()
	assert(latest3["text"] == "three")
	assert(latest3["mode"] == "act")

	# 3b. A full queue (5) refuses further submissions.
	for probe_index in range(5):
		store.submit_input_from_request(
			{"text": "q%d" % probe_index}
		)
	var full = store.submit_input_from_request(
		{"text": "overflow"}
	)
	assert(full["success"] == false)
	assert(full["error"].contains("queue is full"))
	assert(store.pending_requests.size() == 5)

	# 4. Model selection applies to the NEXT turn and
	# survives until changed.
	store.apply_event(
		{
			"event": "model_selected",
			"provider": "zai",
			"model": "glm-4.7-flash",
		}
	)
	assert(store.selected_model == "glm-4.7-flash")
	assert(store.selected_provider == "zai")
	assert(store.model_label == "glm-4.7-flash")

	# 5. session_started offers the model list but keeps
	# the ledger (already covered) and the selection.
	store.apply_event(
		{
			"event": "session_started",
			"session_id": "cc1",
			"model": "gemini-3.5-flash-lite",
			"available_models": [
				{"provider": "gemini", "model": "gemini-3.5-flash-lite"},
				{"provider": "zai", "model": "glm-4.7-flash"},
			],
		}
	)
	assert(store.available_models.size() == 2)
	assert(store.selected_model == "glm-4.7-flash")

	print("control channel cases passed")


func _run_session_isolation_cases() -> void:
	# Session isolation: a fresh session must start with no
	# context overlap, no matter which start path spawned
	# it. Three guards work together: superseded polls for
	# stale processes, the STARTING input freeze, and
	# session-id event filtering.

	store = AIAgentStateStoreScript.new()

	# 1. A session claims the bridge via session_started.
	store.apply_event(
		{
			"event": "session_started",
			"session_id": "sess-a",
		}
	)
	assert(store.session_id == "sess-a")

	store.submit_input_from_request(
		{"text": "live request", "mode": "act"}
	)

	# 2. A poll from a DIFFERENT (older) session is told it
	# has been superseded and consumes NOTHING.
	var stale = store.consume_input_snapshot("sess-old")
	assert(stale["success"] == true)
	assert(stale["superseded"] == true)
	assert(stale["pending"] == false)
	assert(stale["text"] == "")
	assert(store.pending_requests.size() == 1)

	# 3. The active session's poll consumes normally.
	var active = store.consume_input_snapshot("sess-a")
	assert(active["superseded"] == false)
	assert(active["pending"] == true)
	assert(active["text"] == "live request")

	# 4. Events stamped with a foreign session id are
	# dropped: a superseded process can never paint the
	# active session's chat, timeline, or metrics.
	var calls_before: int = store.model_call_count
	store.apply_event(
		{
			"event": "model_response",
			"session_id": "sess-zzz",
			"turn": 9,
			"step": 9,
			"model": "stale",
			"duration_ms": 1.0,
		}
	)
	assert(store.model_call_count == calls_before)

	store.apply_event(
		{
			"event": "model_response",
			"session_id": "sess-a",
			"turn": 1,
			"step": 1,
			"model": "live",
			"duration_ms": 1.0,
		}
	)
	assert(store.model_call_count == calls_before + 1)

	# 5. The STARTING handover freezes input for the
	# recorded (dying) session: queued work cannot be
	# consumed by the old process while the fresh session
	# spawns.
	store.mark_session_starting()
	store.submit_input_from_request(
		{"text": "typed during handover", "mode": "act"}
	)

	var frozen = store.consume_input_snapshot("sess-a")
	assert(frozen["pending"] == false)
	assert(frozen["text"] == "")
	assert(store.pending_requests.size() == 1)

	# An unknown session id during the handover is the
	# INCOMING fresh process (its session_started has not
	# landed yet): it must NOT be told it is superseded.
	var incoming = store.consume_input_snapshot("sess-b")
	assert(incoming["superseded"] == false)
	assert(incoming["pending"] == false)

	# 6. The fresh session's session_started resets every
	# session-scoped state, ends the freeze, and wipes
	# anything still queued for the dead session; the old
	# session id becomes stale for polls.
	store.apply_event(
		{
			"event": "session_started",
			"session_id": "sess-b",
		}
	)
	assert(store.session_starting == false)
	assert(store.session_id == "sess-b")
	assert(store.chat_turns.is_empty())
	assert(store.turn_number == 0)
	assert(store.events.is_empty())
	assert(store.pending_requests.is_empty())

	var fresh = store.consume_input_snapshot("sess-b")
	assert(fresh["superseded"] == false)
	assert(fresh["pending"] == false)

	var old_after = store.consume_input_snapshot("sess-a")
	assert(old_after["superseded"] == true)

	print("session isolation cases passed")


func _init() -> void:

	store = AIAgentStateStoreScript.new()

	_run_store_cases()

	_run_bounds_and_tolerance_cases()

	_run_control_channel_cases()

	_run_session_isolation_cases()

	_run_router_cases()

	print("agent state store cases passed")

	quit()

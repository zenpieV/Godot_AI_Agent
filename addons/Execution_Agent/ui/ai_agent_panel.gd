@tool
extends Control

class_name AIAgentPanel


# ==========================================
# AI Agent bottom panel
# ==========================================
# Observability UI for the agent, rendered entirely with
# native editor widgets so it inherits the editor theme:
# Tree for the timeline/ledger/metrics, TabContainer for the
# four views, RichTextLabel for answers. No custom drawing,
# no hard-coded palette: status colors are looked up from
# the editor theme (success/warning/error/accent) with sane
# fallbacks for headless contexts.
#
# This panel is a MONITOR in phase 1: it renders the state
# store and provides no agent controls. The header keeps a
# reserved right slot showing the approval-gate state so the
# control phase has a home without layout churn later.


const STATUS_LABELS := {
	"ready": "READY",
	"thinking": "THINKING",
	"executing_tool": "EXECUTING TOOL",
	"offline_run": "OFFLINE RUN",
	"waiting_approval": "WAITING APPROVAL",
	"completed": "COMPLETED",
	"needs_attention": "NEEDS ATTENTION",
	"error": "ERROR",
	"session_ended": "SESSION ENDED",
}


# THINKING animates between these two warm tones (a
# gentle color pulse with a matching border) so an
# in-flight model call reads as "alive" at a glance.
# Red stays reserved for errors.

const THINKING_COLOR_A := Color(0.95, 0.60, 0.15)

const THINKING_COLOR_B := Color(1.0, 0.78, 0.38)

const THINKING_PULSE_SPEED := 2.6

# The mode switch's fixed pair. Deliberately NOT the
# theme accent: the user's editor theme renders
# accent_color red, and Act must read BLUE.

const MODE_COLOR_PLAN := Color(0.95, 0.60, 0.15)

const MODE_COLOR_ACT := Color(0.35, 0.55, 0.95)


var store: AIAgentAgentStateStore

# Spawned by the plugin; called when the status button
# acts as Start Session (no agent process running).

var _start_session_callback: Callable


var _status_button: Button

var _status_pill_style: StyleBoxFlat

var _status_detail_label: Label

var _turn_label: Label

var _elapsed_label: Label

var _connection_label: Label

var _model_option: OptionButton

var _tokens_label: Label

var _approval_label: Label
var _new_session_button: Button
var _context_label: Label
var _approve_button: Button
var _deny_button: Button

var _tabs: TabContainer

var _activity_tree: Tree

var _mutations_tree: Tree

var _chat_box: VBoxContainer

var _chat_scroll: ScrollContainer

var _chat_input: LineEdit

var _chat_send_button: Button

var _plan_mode_button: Button

var _metrics_tree: Tree

var _turn_items: Dictionary = {}

var _thinking_phase := 0.0

var _suppress_model_signal := false


func _init() -> void:

	custom_minimum_size = Vector2(0, 240)

	_build_ui()


func setup(
	p_store: AIAgentAgentStateStore,
	start_session_callback: Callable = Callable(),
) -> void:

	store = p_store

	_start_session_callback = start_session_callback

	store.status_changed.connect(
		_refresh_header
	)

	store.events_updated.connect(
		_rebuild_activity
	)

	store.ledger_updated.connect(
		_rebuild_mutations
	)

	store.chat_updated.connect(
		_rebuild_chat
	)

	store.metrics_updated.connect(
		_rebuild_metrics
	)

	_refresh_header()

	_rebuild_activity()

	_rebuild_mutations()

	_rebuild_chat()

	_rebuild_metrics()


func _process(_delta: float) -> void:

	_update_elapsed()

	_animate_thinking()

	# The heartbeat goes stale over TIME, so the dot must
	# refresh continuously, not just on store signals.

	_update_connection_dot()

	var waiting := (
		store != null
		and store.status == "waiting_approval"
		and store.approval_id != ""
	)
	_approve_button.visible = waiting
	_deny_button.visible = waiting
	_approval_label.visible = not waiting
	_update_context_label()

	# STARTING... must not wedge: if the agent process
	# never announces itself, allow another attempt.

	if (
		store != null
		and store.session_starting
		and Time.get_ticks_msec()
		- store.session_starting_ms > 30000
	):
		store.session_starting = false

		_refresh_header()


func _on_new_session_pressed() -> void:
	if store == null or not store.is_session_running():
		return

	if store.session_starting:
		return

	if not _start_session_callback.is_valid():
		return

	# A new session is authoritative IMMEDIATELY: spawn the
	# fresh process right away instead of waiting for the
	# old one to end. When the fresh process announces
	# itself (session_started), the store resets every
	# session-scoped state (chat, turn numbers, metrics)
	# and any older agent process still polling the bridge
	# is told it has been superseded and exits itself. No
	# /exit handoff, so the fresh session can never inherit
	# queued state from the old one.

	store.mark_session_starting()

	var started: bool = _start_session_callback.call()

	if not started:
		store.mark_session_start_failed()

func _on_status_button_pressed() -> void:

	if store == null or store.is_session_running():
		return

	if store.session_starting:
		return

	if not _start_session_callback.is_valid():
		return

	store.mark_session_starting()

	var started: bool = _start_session_callback.call()

	if not started:
		store.mark_session_start_failed()

	_refresh_header()


func _animate_thinking() -> void:

	# The THINKING status gets a warm pulsing pill (and a
	# soft animated border) so an in-flight model call is
	# visible in peripheral vision. Every other status is
	# static.

	if store == null or _status_pill_style == null:
		return

	if store.status == "thinking":

		_thinking_phase += _delta_value() * (
			THINKING_PULSE_SPEED
		)

		var wave := 0.5 + 0.5 * sin(_thinking_phase)

		var pulse := THINKING_COLOR_A.lerp(
			THINKING_COLOR_B,
			wave
		)

		_status_pill_style.bg_color = pulse

		_status_pill_style.set_border_width_all(2)

		_status_pill_style.border_color = pulse.lightened(
			0.35
		)

	else:

		_status_pill_style.set_border_width_all(0)

		_thinking_phase = 0.0


func _delta_value() -> float:

	# _process passes _delta; reading the frame time here
	# keeps the animation self-contained.

	return get_process_delta_time()


# ==========================================
# UI construction
# ==========================================


func _build_ui() -> void:

	var margin := MarginContainer.new()

	margin.set_anchors_preset(
		PRESET_FULL_RECT
	)

	margin.add_theme_constant_override(
		"margin_left", 8
	)

	margin.add_theme_constant_override(
		"margin_top", 6
	)

	margin.add_theme_constant_override(
		"margin_right", 8
	)

	margin.add_theme_constant_override(
		"margin_bottom", 6
	)

	add_child(margin)

	var vbox := VBoxContainer.new()

	vbox.add_theme_constant_override(
		"separation", 6
	)

	margin.add_child(vbox)

	_build_header(vbox)

	_tabs = TabContainer.new()

	_tabs.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)

	vbox.add_child(_tabs)

	# Chat first: it is the primary surface (request in,
	# thinking stream, answer out).

	_build_chat_tab()

	_build_activity_tab()

	_build_mutations_tab()

	_build_metrics_tab()


func _build_header(
	parent: VBoxContainer
) -> void:

	var header := HBoxContainer.new()

	header.add_theme_constant_override(
		"separation", 10
	)

	parent.add_child(header)

	# The status pill is a BUTTON: while no agent process
	# is running it reads START SESSION and spawns the
	# agent via the plugin callback; while a session is
	# live it is a plain (non-interactive) status display.

	_status_button = Button.new()

	_status_pill_style = StyleBoxFlat.new()

	_status_pill_style.set_corner_radius_all(6)

	_status_pill_style.content_margin_left = 10.0

	_status_pill_style.content_margin_right = 10.0

	_status_pill_style.content_margin_top = 3.0

	_status_pill_style.content_margin_bottom = 3.0

	for state_name in [
		"normal", "hover", "pressed", "disabled", "focus",
	]:

		_status_button.add_theme_stylebox_override(
			state_name,
			_status_pill_style
		)

	_status_button.text = "START SESSION"

	_status_button.pressed.connect(
		_on_status_button_pressed
	)

	header.add_child(_status_button)

	_status_detail_label = Label.new()

	_status_detail_label.text = ""

	_status_detail_label.add_theme_color_override(
		"font_color",
		_color("font_disabled_color", Color(0.6, 0.6, 0.6))
	)

	header.add_child(_status_detail_label)

	var spacer := Control.new()

	spacer.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	header.add_child(spacer)

	_turn_label = Label.new()

	_turn_label.text = "-"

	header.add_child(_turn_label)

	_elapsed_label = Label.new()

	_elapsed_label.text = ""

	_elapsed_label.add_theme_color_override(
		"font_color",
		_color("font_disabled_color", Color(0.6, 0.6, 0.6))
	)

	header.add_child(_elapsed_label)

	# Agent-process connection dot: green while the agent
	# is polling the input channel (bridge input mode),
	# gray when unknown (classic stdin CLI), red when the
	# heartbeat went stale.

	_connection_label = Label.new()

	_connection_label.text = "- agent"

	_connection_label.tooltip_text = (
		"Agent-process connection. Green: the agent "
		+ "process is polling the input channel. Gray: "
		+ "unknown (classic CLI mode). Red: the "
		+ "heartbeat went stale."
	)

	header.add_child(_connection_label)

	# Model selector: lists every provider's configured
	# model; the choice applies to the NEXT turn.

	_model_option = OptionButton.new()

	_model_option.tooltip_text = (
		"Model used from the NEXT turn on. The list is "
		+ "the configured model per provider."
	)

	_model_option.item_selected.connect(
		_on_model_selected
	)

	header.add_child(_model_option)

	_tokens_label = Label.new()

	_tokens_label.text = ""

	header.add_child(_tokens_label)

	# Reserved slot for the control phase: the approval
	# bar renders its off state so the layout already
	# has a home for Approve/Deny later.

	_approval_label = Label.new()

	_approval_label.text = "approval gates: off"

	_approval_label.tooltip_text = (
		"Mutation approval gates are not configured. "
		+ "The agent executes verified tools autonomously."
	)

	_approval_label.add_theme_color_override(
		"font_color",
		_color("font_disabled_color", Color(0.6, 0.6, 0.6))
	)

	header.add_child(_approval_label)

	# Approval gate controls: visible only while a
	# mutation waits for the user's decision.
	_approve_button = Button.new()
	_approve_button.text = "Approve"
	_approve_button.visible = false
	_approve_button.pressed.connect(
		_on_approval_pressed.bind(true)
	)
	header.add_child(_approve_button)

	_deny_button = Button.new()
	_deny_button.text = "Deny"
	_deny_button.visible = false
	_deny_button.pressed.connect(
		_on_approval_pressed.bind(false)
	)
	header.add_child(_deny_button)
	# New Session: ends the running agent process via
	# /exit (queued like any request) and spawns a fresh
	# one as soon as the session_ended event lands. The
	# fresh process starts with an empty conversation.

	_new_session_button = Button.new()

	_new_session_button.text = "New Session"

	_new_session_button.tooltip_text = (
		"Starts a fresh agent process with an empty "
		+ "conversation right away; the previous "
		+ "process exits itself. Use when the "
		+ "context meter runs high or the session "
		+ "is stuck."
	)

	_new_session_button.pressed.connect(
		_on_new_session_pressed
	)

	header.add_child(_new_session_button)

	# Context meter: approximate conversation size (the
	# last prompt includes the whole conversation) against
	# the provider's configured limit.

	_context_label = Label.new()

	_context_label.text = ""

	_context_label.tooltip_text = (
		"Approximate conversation size (last prompt "
		+ "tokens) against the configured limit."
	)

	header.add_child(_context_label)


func _make_tree(
	columns: Array,
	expand_last: bool = true
) -> Tree:

	var tree := Tree.new()

	tree.columns = columns.size()

	tree.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)

	tree.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	for index in range(columns.size()):

		tree.set_column_title(
			index,
			columns[index]
		)

		tree.set_column_expand(index, true)

	tree.column_titles_visible = true

	return tree


func _add_tab(
	tab_container: TabContainer,
	control: Control,
	title: String
) -> void:

	# Godot 4.7 TabContainer has no add_tab(): the child is
	# added first, then titled by index.

	tab_container.add_child(control)

	tab_container.set_tab_title(
		control.get_index(),
		title
	)


func _build_activity_tab() -> void:

	_activity_tree = _make_tree(
		["Time", "Event", "Detail"]
	)

	_activity_tree.item_activated.connect(
		_on_activity_activated
	)

	_add_tab(_tabs, _activity_tree, "Activity")


func _build_mutations_tab() -> void:

	_mutations_tree = _make_tree(
		[
			"Time",
			"Action",
			"Target",
			"Verification",
			"Undoable",
		]
	)

	_mutations_tree.item_activated.connect(
		_on_mutation_activated
	)

	_add_tab(_tabs, _mutations_tree, "Mutations")


func _build_chat_tab() -> void:

	var vbox := VBoxContainer.new()

	vbox.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)

	vbox.add_theme_constant_override(
		"separation", 6
	)

	var scroll := ScrollContainer.new()

	_chat_scroll = scroll

	scroll.horizontal_scroll_mode = (
		ScrollContainer.SCROLL_MODE_DISABLED
	)

	scroll.size_flags_vertical = (
		Control.SIZE_EXPAND_FILL
	)

	_chat_box = VBoxContainer.new()

	_chat_box.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	_chat_box.add_theme_constant_override(
		"separation", 8
	)

	scroll.add_child(_chat_box)

	vbox.add_child(scroll)

	# The input bar: submits the next user request to the
	# agent's bridge input queue (bridge input mode) and
	# renders as a user bubble as soon as the agent picks
	# the request up. /exit keeps its CLI meaning: it ends
	# the agent process.

	var input_bar := HBoxContainer.new()

	input_bar.add_theme_constant_override(
		"separation", 6
	)

	# Plan/Act mode switch: shows the CURRENT mode as its
	# text (Plan = orange, Act = blue); clicking switches to
	# the other mode, which applies to every request sent
	# while it is selected. Default is Act.

	_plan_mode_button = Button.new()

	_plan_mode_button.toggle_mode = true

	_plan_mode_button.tooltip_text = (
		"Plan: the agent may only inspect and plan - "
		+ "mutations are refused; the turn returns a "
		+ "workflow plan. Act: normal execution. Click "
		+ "to switch; applies to submitted requests."
	)

	_plan_mode_button.toggled.connect(
		_on_plan_mode_toggled
	)

	_plan_mode_button.set_pressed_no_signal(false)

	_apply_mode_button_style(false)

	input_bar.add_child(_plan_mode_button)

	_chat_input = LineEdit.new()

	_chat_input.placeholder_text = (
		"Type a request... (/exit ends the agent process)"
	)

	_chat_input.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	_chat_input.text_submitted.connect(
		_on_chat_input_submitted
	)

	input_bar.add_child(_chat_input)

	_chat_send_button = Button.new()

	_chat_send_button.text = "Send"

	_chat_send_button.pressed.connect(
		_on_chat_input_submitted.bind("")
	)

	input_bar.add_child(_chat_send_button)

	vbox.add_child(input_bar)

	_add_tab(_tabs, vbox, "Chat")


func _build_metrics_tab() -> void:

	_metrics_tree = _make_tree(
		[
			"Call",
			"Turn.Step",
			"Model",
			"Prompt",
			"Output",
			"Duration",
		],
		false
	)

	_add_tab(_tabs, _metrics_tree, "Metrics")


# ==========================================
# Refresh
# ==========================================


func _refresh_header() -> void:

	if store == null:
		return

	if not store.is_session_running():

		# No agent process: the status button IS the
		# Start Session button.

		if store.session_starting:

			_status_button.text = "STARTING..."

			_status_button.disabled = true

			_status_pill_style.bg_color = (
				THINKING_COLOR_A
			)

			_status_button.add_theme_color_override(
				"font_pressed_color",
				Color(0.1, 0.12, 0.14)
			)

		else:

			_status_button.text = "START SESSION"

			_status_button.disabled = false

			_status_pill_style.bg_color = _color(
				"success_color",
				Color(0.45, 0.8, 0.45)
			)

		_status_button.add_theme_color_override(
			"font_color",
			Color(0.1, 0.12, 0.14)
		)

		_status_button.add_theme_color_override(
			"font_disabled_color",
			Color(0.1, 0.12, 0.14)
		)

		_status_detail_label.text = (
			store.status_detail
			if store.status_detail != ""
			else "No agent process running."
		)

	else:

		var status_name := str(
			store.status
		)

		_status_button.text = str(
			STATUS_LABELS.get(
				status_name,
				status_name.to_upper()
			)
		)

		_status_button.disabled = true

		_status_pill_style.bg_color = _status_color(
			status_name
		)

		_status_button.add_theme_color_override(
			"font_disabled_color",
			Color(0.1, 0.12, 0.14)
			if not store.is_busy()
			else Color.WHITE
		)

		_status_detail_label.text = store.status_detail

	if store.turn_number > 0:
		_turn_label.text = "turn %d - step %d" % [
			store.turn_number,
			store.step_number,
		]
	else:
		_turn_label.text = (
			"session %s" % store.session_id
			if store.session_id != ""
			else "no session"
		)

	_update_connection_dot()

	_refresh_model_selector()

	if store.model_call_count > 0:
		_tokens_label.text = "%d calls - %s in / %s out" % [
			store.model_call_count,
			_thousands(store.total_prompt_tokens),
			_thousands(store.total_output_tokens),
		]
	else:
		_tokens_label.text = ""

	if store.session_id != "" and store.status != (
		"session_ended"
	):
		_chat_input.editable = true

		_chat_send_button.disabled = false

	else:

		_chat_input.editable = false

		_chat_send_button.disabled = true

	_update_elapsed()


func _on_approval_pressed(approved: bool) -> void:
	if store == null or store.approval_id == "":
		return

	_post_bridge_json(
		"/agent_approval",
		{"id": store.approval_id, "approved": approved},
		Callable()
	)

func _update_context_label() -> void:

	if store == null or _context_label == null:
		return

	if store.context_limit <= 0 or store.model_call_count == 0:
		_context_label.text = ""
		return

	var fraction := float(store.context_used_tokens) / float(
		store.context_limit
	)

	_context_label.text = "ctx %s/%s (%d%%)" % [
		_thousands(store.context_used_tokens),
		_thousands(store.context_limit),
		int(fraction * 100.0),
	]

	var meter_color := _color(
		"success_color", Color(0.45, 0.8, 0.45)
	)

	if fraction > 0.8:
		meter_color = _color(
			"error_color", Color(0.9, 0.3, 0.3)
		)
	elif fraction > 0.5:
		meter_color = _color(
			"warning_color", Color(0.95, 0.75, 0.2)
		)

	_context_label.add_theme_color_override(
		"font_color", meter_color
	)


func _update_connection_dot() -> void:

	var dot_color: Color

	if store.last_input_poll_ms == 0:

		dot_color = _color(
			"font_disabled_color",
			Color(0.55, 0.55, 0.55)
		)

		_connection_label.text = "- agent"

	elif store.is_agent_connected():

		dot_color = _color(
			"success_color",
			Color(0.45, 0.8, 0.45)
		)

		_connection_label.text = "- agent"

	else:

		dot_color = _color(
			"error_color",
			Color(0.9, 0.3, 0.3)
		)

		_connection_label.text = "- agent stale"

	_connection_label.add_theme_color_override(
		"font_color",
		dot_color
	)


func _refresh_model_selector() -> void:

	# Rebuild the dropdown from the session's offered
	# models and sync the selection with the ACTIVE model
	# (store.model_label follows request_sent/model_
	# response events after a switch).

	_suppress_model_signal = true

	_model_option.clear()

	var selected_index := -1

	for index in range(store.available_models.size()):

		var entry: Dictionary = store.available_models[
			index
		]

		var model_name := str(entry.get("model", ""))

		var provider_name := str(
			entry.get("provider", "")
		)

		_model_option.add_item(
			model_name + "  (" + provider_name + ")",
			index
		)

		_model_option.set_item_metadata(
			index,
			{"provider": provider_name, "model": model_name}
		)

		if model_name == store.model_label:
			selected_index = index

	if selected_index >= 0:
		_model_option.select(selected_index)

	_suppress_model_signal = false


func _update_elapsed() -> void:

	if store == null:
		return

	if store.turn_number > 0:

		_elapsed_label.text = _format_mmss(
			store.turn_elapsed_seconds()
		)

	else:

		_elapsed_label.text = ""


func _rebuild_activity() -> void:

	if store == null or _activity_tree == null:
		return

	_activity_tree.clear()

	_turn_items.clear()

	_activity_tree.create_item()

	var last_item: TreeItem = null

	for event in store.events:

		var turn := int(event.get("turn", 0))

		var turn_item := _get_turn_item(turn)

		var row := _activity_tree.create_item(turn_item)

		row.set_text(
			0,
			_format_mmss_from_ms(
				int(event.get("ts_ms", 0))
			)
		)

		row.set_text(
			1,
			str(event.get("kind", ""))
		)

		row.set_text(
			2,
			_row_summary(event)
		)

		# TreeItem has no tooltip_text property (that is a
		# Control property); the tooltip is per-column -
		# assign it to the summary column. Assigning the
		# Control property throws a script error that
		# aborts the whole rebuild. (Same class of bug as
		# the removed `collapsible` assignment - Godot 4
		# TreeItem has neither property.)

		row.set_tooltip_text(
			2,
			str(event.get("detail", ""))
		)

		_apply_kind_color(row, str(event.get("kind", "")))

		last_item = row

	if last_item != null:
		_activity_tree.scroll_to_item(last_item)


func _row_summary(
	event: Dictionary
) -> String:

	var summary := str(event.get("summary", ""))

	var detail := str(event.get("detail", ""))

	if detail.is_empty():
		return summary

	return summary + "  -  " + detail


func _get_turn_item(
	turn: int
) -> TreeItem:

	if _turn_items.has(turn):
		return _turn_items[turn]

	var root := _activity_tree.get_root()

	var item := _activity_tree.create_item(root)

	if turn > 0:

		item.set_text(
			0,
			"Turn %d" % turn
		)

		if store != null and turn == store.turn_number:
			item.set_text(
				2,
				store.request_preview
			)

	else:

		item.set_text(0, "Session")

	# TreeItem is not a Control: it has no
	# custom_minimum_size. Row height comes from the Tree's
	# theme. Assigning it throws a script error that
	# aborts the rebuild and leaves _turn_items unrecorded
	# (duplicate turn headers on every event).

	_turn_items[turn] = item

	return item


func _apply_kind_color(
	row: TreeItem,
	kind: String
) -> void:

	var tint: Color

	match kind:

		"tool_result":
			tint = _color(
				"success_color",
				Color(0.4, 0.8, 0.4)
			)

		"error":
			tint = _color(
				"error_color",
				Color(0.9, 0.3, 0.3)
			)

		"blocked", "validation", "attention":
			tint = _color(
				"warning_color",
				Color(0.95, 0.75, 0.2)
			)

		"compaction", "session":
			tint = _color(
				"font_disabled_color",
				Color(0.6, 0.6, 0.6)
			)

		"answer":
			tint = _color(
				"accent_color",
				Color(0.4, 0.6, 1.0)
			)

		_:
			return

	row.set_custom_color(1, tint)


func _rebuild_mutations() -> void:

	if store == null or _mutations_tree == null:
		return

	_mutations_tree.clear()

	_mutations_tree.create_item()

	for entry in store.ledger:

		var row := _mutations_tree.create_item()

		row.set_text(
			0,
			_format_mmss_from_ms(
				int(entry.get("ts_ms", 0))
			)
		)

		row.set_text(
			1,
			str(entry.get("action", ""))
		)

		row.set_text(
			2,
			str(entry.get("target", ""))
		)

		row.set_text(
			3,
			str(entry.get("verification", ""))
		)

		row.set_text(
			4,
			"yes" if bool(
				entry.get("undoable", false)
			) else "no (file-level)"
		)

		row.tooltip_text = (
			"Undoable through the editor (Ctrl+Z)."
			if bool(entry.get("undoable", false))
			else (
				"File-level change, not undoable "
				+ "through the editor."
			)
		)

		var verification := str(
			entry.get("verification", "")
		)

		var tint: Color

		if not bool(entry.get("success", false)):
			tint = _color(
				"error_color",
				Color(0.9, 0.3, 0.3)
			)
		elif verification == "verified":
			tint = _color(
				"success_color",
				Color(0.4, 0.8, 0.4)
			)
		else:
			tint = _color(
				"warning_color",
				Color(0.95, 0.75, 0.2)
			)

		row.set_custom_color(3, tint)


func _on_plan_mode_toggled(pressed: bool) -> void:

	_apply_mode_button_style(pressed)


func _apply_mode_button_style(plan_selected: bool) -> void:

	# The button displays the CURRENT mode and carries its
	# color: Plan = orange, Act = blue (both fixed - the
	# user's editor theme renders accent_color red). Every
	# toggle state is overridden, including hover_pressed:
	# a toggled-on button that is hovered would otherwise
	# fall back to the theme's grey default. Focus is a
	# border-only box on top instead of a full repaint.

	var base: Color

	var hover: Color

	var label: String

	if plan_selected:

		base = MODE_COLOR_PLAN

		hover = Color(1.0, 0.78, 0.38)

		label = "Plan"

	else:

		base = MODE_COLOR_ACT

		hover = base.lightened(0.18)

		label = "Act"

	_plan_mode_button.text = label

	for state_name in [
		"normal",
		"hover",
		"pressed",
		"hover_pressed",
		"disabled",
	]:

		var style := StyleBoxFlat.new()

		style.set_corner_radius_all(6)

		style.content_margin_left = 10.0

		style.content_margin_right = 10.0

		style.content_margin_top = 3.0

		style.content_margin_bottom = 3.0

		style.bg_color = (
			hover
			if state_name in ["hover", "hover_pressed"]
			else base
		)

		_plan_mode_button.add_theme_stylebox_override(
			state_name,
			style
		)

	var focus_style := StyleBoxFlat.new()

	focus_style.set_corner_radius_all(6)

	focus_style.bg_color = Color(
		base.r, base.g, base.b, 0.35
	)

	focus_style.set_border_width_all(2)

	focus_style.border_color = Color(1, 1, 1, 0.6)

	_plan_mode_button.add_theme_stylebox_override(
		"focus",
		focus_style
	)

	# Dark text on both warm and blue fills keeps the
	# label readable without a second font color set.

	for font_state in [
		"font_color",
		"font_hover_color",
		"font_pressed_color",
		"font_hover_pressed_color",
		"font_focus_color",
	]:

		_plan_mode_button.add_theme_color_override(
			font_state,
			Color(0.1, 0.12, 0.14)
		)


func _on_chat_input_submitted(
	text: String = ""
) -> void:

	# Bound to both the Send button (default "") and the
	# LineEdit's text_submitted (which passes the text).

	var request_text := text

	if request_text == "":
		request_text = _chat_input.text

	request_text = request_text.strip_edges()

	if request_text.is_empty():
		return

	_chat_input.clear()

	_post_bridge_json(
		"/agent_input",
		{
			"text": request_text,
			"mode": (
				"plan"
				if _plan_mode_button.button_pressed
				else "act"
			),
		},
		func(response: Dictionary) -> void:
			if not response.get("success", false):
				# Put the text back so nothing the
				# user typed is silently lost.
				_chat_input.text = request_text
				_chat_input.caret_column = (
					_chat_input.text.length()
				)
	)


func _on_model_selected(index: int) -> void:

	if _suppress_model_signal:
		return

	var meta: Variant = _model_option.get_item_metadata(
		index
	)

	if not (meta is Dictionary):
		return

	var entry: Dictionary = meta

	_post_bridge_json(
		"/agent_event",
		{
			"event": "model_selected",
			# Stamped with the active session so the
			# store's legacy-event filter (events with
			# no session id are dropped while a session
			# is active) never swallows panel traffic.
			"session_id": store.session_id,
			"provider": str(entry.get("provider", "")),
			"model": str(entry.get("model", "")),
		},
		Callable()
	)


func _post_bridge_json(
	path: String,
	payload: Dictionary,
	on_done: Callable
) -> void:

	# One-shot HTTPRequest per POST: fire-and-forget for
	# events, with an optional response callback for
	# submissions whose text must survive failures.

	var http := HTTPRequest.new()

	http.timeout = 3.0

	add_child(http)

	http.request_completed.connect(
		func(
			_result: int,
			_code: int,
			_headers: PackedStringArray,
			body: PackedByteArray,
		) -> void:
			http.queue_free()

			if not on_done.is_valid():
				return

			var parsed: Dictionary = {}

			var decoded: Variant = JSON.parse_string(
				body.get_string_from_utf8()
			)

			if decoded is Dictionary:
				parsed = decoded

			on_done.call(parsed)
	)

	var body := JSON.stringify(payload)

	var error := http.request(
		"http://127.0.0.1:%d%s" % [
			store.bridge_port if store != null else 8081,
			path,
		],
		["Content-Type: application/json"],
		HTTPClient.METHOD_POST,
		body
	)

	if error != OK:

		# Request never started: release and inform the
		# callback with a failure so caller-side recovery
		# (restoring typed text) still runs.

		http.queue_free()

		if on_done.is_valid():
			on_done.call({})


func _on_mutation_activated() -> void:

	var selected := _mutations_tree.get_selected()

	if selected == null:
		return

	var entry_index := selected.get_index()

	if store == null or entry_index >= store.ledger.size():
		return

	var target_path := str(
		store.ledger[entry_index].get("target_path", "")
	)

	if target_path.is_empty():
		return

	if FileAccess.file_exists(target_path):

		EditorInterface.get_file_system_dock().navigate_to_path(
			target_path
		)


func _on_activity_activated() -> void:

	# Reserved for phase 2: jumping from a mutation row to
	# its node/resource. Double-click currently does
	# nothing on the activity timeline.

	pass


func _rebuild_chat() -> void:

	if store == null or _chat_box == null:
		return

	for child in _chat_box.get_children():
		child.queue_free()

	# Chat-LLM layout, one block per turn: the user's
	# request (accent-tinted bubble), then while the turn
	# is in flight ONE dim thinking line whose text is the
	# latest decision reason (each new reason replaces the
	# previous in place), and once the turn completes the
	# thinking line disappears entirely and only the bright
	# answer bubble remains.

	for turn_entry in store.chat_turns:

		var turn := int(turn_entry.get("turn", 0))

		var request := str(turn_entry.get("request", ""))

		var thinking := str(turn_entry.get("thinking", ""))

		var final_answer := str(
			turn_entry.get("final_answer", "")
		)

		var completed := bool(
			turn_entry.get("completed", false)
		)

		_chat_box.add_child(
			_make_user_bubble(
				turn,
				request,
				str(turn_entry.get("mode", "act"))
			)
		)

		if not completed:

			if not thinking.is_empty():

				_chat_box.add_child(
					_make_thinking_line(thinking)
				)

			else:

				_chat_box.add_child(
					_make_thinking_line("...")
				)

			# A failed model call (quota exhausted,
			# provider outage) must be visible exactly
			# where the user is waiting - otherwise a
			# dead session reads as a hang.

			var turn_error := str(
				turn_entry.get("error", "")
			)

			if not turn_error.is_empty():

				_chat_box.add_child(
					_make_error_line(turn_error)
				)

		if completed:

			_chat_box.add_child(
				_make_answer_bubble(turn, final_answer)
			)

	await _scroll_chat_to_bottom()


func _scroll_chat_to_bottom() -> void:

	# New content must always be visible without manual
	# scrolling: after a rebuild, wait one frame for the
	# container layout to settle, then pin the scrollbar
	# to the bottom. The panel may not be inside the tree
	# yet during plugin setup — nothing to scroll then.

	if _chat_scroll == null or not is_inside_tree():
		return

	await get_tree().process_frame

	if _chat_scroll == null or not is_instance_valid(
		_chat_scroll
	):
		return

	_chat_scroll.scroll_vertical = int(
		_chat_scroll.get_v_scroll_bar().max_value
	)


func _make_user_bubble(
	turn: int,
	request: String,
	mode: String = "act"
) -> Control:

	var panel := PanelContainer.new()

	var style := StyleBoxFlat.new()

	style.set_corner_radius_all(8)

	style.content_margin_left = 10.0

	style.content_margin_right = 10.0

	style.content_margin_top = 6.0

	style.content_margin_bottom = 6.0

	# The user bubble mirrors the mode button's color:
	# Plan turns are orange, Act turns are blue - the
	# same fixed pair the button displays (fixed, not
	# accent: the user's editor theme renders accent
	# red).

	if mode == "plan":

		style.bg_color = Color(
			MODE_COLOR_PLAN.r,
			MODE_COLOR_PLAN.g,
			MODE_COLOR_PLAN.b,
			0.18
		)

	else:

		style.bg_color = Color(
			MODE_COLOR_ACT.r,
			MODE_COLOR_ACT.g,
			MODE_COLOR_ACT.b,
			0.18
		)

	panel.add_theme_stylebox_override(
		"panel",
		style
	)

	var label := Label.new()

	var mode_tag := (
		"  -  PLAN"
		if mode == "plan"
		else ""
	)

	label.text = "You - Turn %d%s\n%s" % [
		turn,
		mode_tag,
		request if not request.is_empty() else "(request)",
	]

	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	label.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	panel.add_child(label)

	return panel


func _make_thinking_line(
	reason: String
) -> Control:

	var label := Label.new()

	label.text = "· %s" % reason

	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	label.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	label.add_theme_color_override(
		"font_color",
		_color(
			"font_disabled_color",
			Color(0.6, 0.6, 0.6)
		)
	)

	label.add_theme_font_size_override(
		"font_size",
		12
	)

	return label


func _make_error_line(
	error_text: String
) -> Control:

	var label := Label.new()

	label.text = "⚠ %s" % error_text

	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART

	label.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	# Red is reserved for errors - this is one. Fixed
	# color, not the theme accent (which renders red in
	# some themes and is reserved for other states).

	label.add_theme_color_override(
		"font_color",
		Color(0.85, 0.35, 0.35)
	)

	label.add_theme_font_size_override(
		"font_size",
		12
	)

	return label


func _make_answer_bubble(
	turn: int,
	final_answer: String
) -> Control:

	var panel := PanelContainer.new()

	var style := StyleBoxFlat.new()

	style.set_corner_radius_all(8)

	style.content_margin_left = 10.0

	style.content_margin_right = 10.0

	style.content_margin_top = 6.0

	style.content_margin_bottom = 6.0

	style.bg_color = _color(
		"base_color",
		Color(0.2, 0.2, 0.22)
	)

	panel.add_theme_stylebox_override(
		"panel",
		style
	)

	var vbox := VBoxContainer.new()

	panel.add_child(vbox)

	var title := Label.new()

	title.text = "Agent - Turn %d" % turn

	title.add_theme_font_size_override(
		"font_size",
		12
	)

	title.add_theme_color_override(
		"font_color",
		_color(
			"success_color",
			Color(0.45, 0.8, 0.45)
		)
	)

	vbox.add_child(title)

	var body := RichTextLabel.new()

	body.text = final_answer

	# The answer is the turn's RESULT: render it bright
	# and prominent, never dim like the thinking line.

	body.add_theme_color_override(
		"default_color",
		Color(0.96, 0.96, 0.96)
	)

	body.fit_content = true

	body.selection_enabled = true

	body.size_flags_horizontal = (
		Control.SIZE_EXPAND_FILL
	)

	body.custom_minimum_size = Vector2(0, 24)

	vbox.add_child(body)

	return panel


func _rebuild_metrics() -> void:

	if store == null or _metrics_tree == null:
		return

	_metrics_tree.clear()

	var root := _metrics_tree.create_item()

	for entry in store.metrics:

		var row := _metrics_tree.create_item(root)

		row.set_text(
			0,
			str(entry.get("call", ""))
		)

		row.set_text(
			1,
			"%s.%s" % [
				str(entry.get("turn", 0)),
				str(entry.get("step", 0)),
			]
		)

		row.set_text(
			2,
			str(entry.get("model", ""))
		)

		row.set_text(
			3,
			_token_cell(entry.get("prompt_tokens", -1))
		)

		row.set_text(
			4,
			_token_cell(entry.get("output_tokens", -1))
		)

		row.set_text(
			5,
			"%s ms" % str(entry.get("duration_ms", "?"))
		)

	var totals := _metrics_tree.create_item(root)

	totals.set_text(0, "SUM")

	totals.set_text(
		2,
		"%d call(s), %d without usage data" % [
			store.model_call_count,
			store.usage_unavailable_count,
		]
	)

	totals.set_text(
		3,
		_thousands(store.total_prompt_tokens)
	)

	totals.set_text(
		4,
		_thousands(store.total_output_tokens)
	)


# ==========================================
# Helpers
# ==========================================


func _status_color(
	status_name: String
) -> Color:

	match status_name:

		"ready", "completed":
			return _color(
				"success_color",
				Color(0.45, 0.8, 0.45)
			)

		"thinking":
			# Base tone for THINKING; _process keeps it
			# pulsing between the two warm tones while
			# the model call is in flight.
			return THINKING_COLOR_A

		"executing_tool", "offline_run":
			return _color(
				"accent_color",
				Color(0.35, 0.55, 0.95)
			)

		"waiting_approval", "needs_attention":
			return _color(
				"warning_color",
				Color(0.95, 0.75, 0.2)
			)

		"error":
			return _color(
				"error_color",
				Color(0.9, 0.3, 0.3)
			)

		_:
			return _color(
				"font_disabled_color",
				Color(0.55, 0.55, 0.55)
			)


func _color(
	theme_name: String,
	fallback: Color
) -> Color:

	if is_inside_tree():

		# Returns the editor theme color when present;
		# Theme.get_theme_color falls back to a default
		# Color (never null) when the name is unknown,
		# which is acceptable for a monitor.

		return get_theme_color(
			theme_name,
			"Editor"
		)

	return fallback


func _format_mmss_from_ms(
	ms: int
) -> String:

	if ms <= 0:
		return ""

	var total_seconds := int(ms / 1000.0)

	return "%02d:%02d" % [
		int(total_seconds / 60.0),
		total_seconds % 60,
	]


func _format_mmss(
	seconds: float
) -> String:

	var total_seconds := int(seconds)

	return "%02d:%02d" % [
		int(total_seconds / 60.0),
		total_seconds % 60,
	]


func _thousands(
	value: int
) -> String:

	if value < 0:
		return "?"

	var digits := str(value)

	var result := ""

	var count := 0

	for index in range(digits.length() - 1, -1, -1):

		result = digits[index] + result

		count += 1

		if (
			count % 3 == 0
			and index > 0
		):
			result = "," + result

	return result


func _token_cell(
	value: int
) -> String:

	if value < 0:
		return "n/a"

	return _thousands(value)

@tool
extends EditorDebuggerPlugin

class_name AIAgentDebuggerCapture


# Runtime output capture for the agent.
#
# The editor's debugger receives every error and stdout
# message emitted by a game run via EditorInterface play
# methods. By claiming the built-in "error" and "output"
# captures, this plugin receives copies of those messages
# and buffers them so the agent can read what a running
# game actually printed - the feedback half of the
# playtest loop (run_scene -> get_runtime_output ->
# stop_run) - without any instrumentation inside the
# user's game.
#
# The buffer is a bounded FIFO: when full, the oldest
# entries are dropped and the drop count is reported so
# the agent never mistakes a truncated buffer for a
# complete log.

const MAX_ENTRIES := 500

const MAX_TEXT_LENGTH := 1000

var _entries: Array = []

var _dropped := 0


func _init() -> void:

	print("AI Agent debugger capture initialized.")


func _has_capture(capture: String) -> bool:

	print("AI Agent debugger capture queried for: ", capture)

	return capture == "error" or capture == "output"


func _capture(
	message: String,
	data: Array,
	session_id: int
) -> bool:

	print("AI Agent debugger capture received: ", message, " data_size=", data.size())

	var kind := "output"

	if message.begins_with("error"):
		kind = "error"

	var text := _extract_text(data)

	if text.is_empty():
		return true

	if _entries.size() >= MAX_ENTRIES:

		_entries.pop_front()

		_dropped += 1

	_entries.append(
		{
			"kind": kind,
			"text": text,
			"session_id": session_id,
		}
	)

	return true


func _extract_text(data: Array) -> String:

	# Error and output messages carry differently shaped
	# payloads depending on the engine path that emitted
	# them. Extract defensively: prefer the first string
	# element, otherwise join the printable elements.
	# Never raise on unexpected shapes.

	var parts: Array = []

	for element in data:

		if element == null:
			continue

		parts.append(str(element))

	if parts.is_empty():
		return ""

	var text := " ".join(parts)

	if text.length() > MAX_TEXT_LENGTH:

		text = (
			text.substr(0, MAX_TEXT_LENGTH)
			+ "..."
		)

	return text


func get_entries(
	clear: bool
) -> Dictionary:

	var entries := _entries.duplicate(true)

	var dropped := _dropped

	if clear:

		_entries.clear()

		_dropped = 0

	return {
		"entries": entries,
		"count": entries.size(),
		"dropped": dropped,
		"buffer_full": _entries.size() >= MAX_ENTRIES,
	}


func clear_entries() -> void:

	_entries.clear()

	_dropped = 0

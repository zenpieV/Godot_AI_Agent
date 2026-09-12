@tool
extends RefCounted

class_name AIAgentRuntimeTools


var editor_interface: EditorInterface
# The capture is typed loosely on purpose: the
# EditorDebuggerPlugin base class only exists inside the
# editor, and a hard type reference would break headless
# parsing of this script.
var debugger_capture


func _init(
	p_editor_interface: EditorInterface,
	p_debugger_capture
) -> void:

	editor_interface = p_editor_interface

	debugger_capture = p_debugger_capture


# ==========================================
# Runtime tools
# ==========================================
# The playtest loop: run the game from the editor, read
# the output and errors the running game emits (captured
# through the editor debugger - no instrumentation inside
# the user's game), and stop it. This gives the agent
# behavioral feedback for its own work: parsing proves
# code compiles, running proves it works.
#
# All three tools require the running editor and report
# the explicit unavailable error headless. Running and
# stopping are process-control operations, not scene
# mutations: they report undoable: false.


func _normalize_runtime_scene_path(
	raw_path,
	action_name: String
) -> Dictionary:

	if raw_path == null:
		return {"ok": true, "scene_path": ""}

	if typeof(raw_path) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				action_name
				+ " scene_path must be a string."
			)
		}

	var scene_path: String = (
		str(raw_path).strip_edges()
	)

	if scene_path.is_empty():
		return {"ok": true, "scene_path": ""}

	if not scene_path.begins_with("res://"):

		scene_path = (
			"res://"
			+ scene_path
		)

	if scene_path.contains("\\"):

		return {
			"success": false,
			"error": (
				action_name
				+ " scene_path must use "
				+ "forward slashes."
			)
		}

	if scene_path.contains(".."):

		return {
			"success": false,
			"error": (
				action_name
				+ " scene_path must not "
				+ "contain directory traversal."
			)
		}

	if not scene_path.ends_with(".tscn"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a scene_path "
				+ "ending in .tscn."
			)
		}

	if scene_path.get_file() == ".tscn":

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "scene file name."
			)
		}

	if not FileAccess.file_exists(scene_path):

		return {
			"success": false,
			"error": (
				action_name + ": scene not found: "
				+ scene_path
			)
		}

	return {
		"ok": true,
		"scene_path": scene_path
	}


# ==========================================
# run_scene
# ==========================================


func run_scene_from_request(
	data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "run_scene",
			"error": (
				"run_scene requires the running "
				+ "Godot editor."
			)
		}

	var path_check := (
		_normalize_runtime_scene_path(
			data.get("scene_path"),
			"run_scene"
		)
	)

	if not path_check.get("ok", false):
		return path_check

	# Deterministic single-session contract: never run two
	# games at once. The agent stops one run before
	# starting another.

	if editor_interface.is_playing_scene():

		return {
			"success": false,
			"action": "run_scene",
			"error": (
				"A game is already running ("
				+ str(editor_interface.get_playing_scene())
				+ "). Call stop_run first."
			)
		}

	var scene_path: String = path_check["scene_path"]

	# The capture buffer is cleared at the run boundary so
	# get_runtime_output only ever reports THIS run's
	# output - previous runs' entries never leak in.

	if debugger_capture != null:

		debugger_capture.clear_entries()

	if scene_path.is_empty():

		editor_interface.play_main_scene()
	else:

		editor_interface.play_custom_scene(scene_path)

	# Post-operation verification: the editor reports a
	# playing scene. The play request launches the game as
	# a separate process, so a short bounded blocking wait
	# (no frame dependency) is applied before checking.
	# 1.5 s: long enough for process spawn here, and half
	# of the previous editor-freeze window.

	var waited_ms := 0

	while waited_ms < 1500 \
			and not editor_interface.is_playing_scene():

		OS.delay_msec(100)

		waited_ms += 100

	var is_playing: bool = (
		editor_interface.is_playing_scene()
	)

	var playing_scene: String = ""

	if is_playing:

		playing_scene = str(
			editor_interface.get_playing_scene()
		)

	# Success policy: an unverified run is a failure -
	# reporting success while nothing is playing made a
	# failed launch indistinguishable from a working one.

	return {
		"success": is_playing,
		"action": "run_scene",
		"message": (
			"Game is running. Use get_runtime_output to read "
			+ "its errors and output, and stop_run to end it."
			if is_playing
			else "run_scene could not verify that the "
			+ "game started (no playing scene after 1.5 s)."
		),
		"requested_scene": (
			scene_path
			if not scene_path.is_empty()
			else "<main scene>"
		),
		"playing_scene": playing_scene,
		"is_playing": is_playing,
		"changed": true,
		"verified_run": is_playing,
		"undoable": false
	}


# ==========================================
# stop_run
# ==========================================


func stop_run_from_request(
	_data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "stop_run",
			"error": (
				"stop_run requires the running "
				+ "Godot editor."
			)
		}

	# Deterministic idempotent case: nothing is running.

	if not editor_interface.is_playing_scene():

		return {
			"success": true,
			"action": "stop_run",
			"message": (
				"No game is currently running; no "
				+ "change was made."
			),
			"changed": false,
			"is_playing": false,
			"verified_stop": true,
			"undoable": false
		}

	var stopped_scene: String = str(
		editor_interface.get_playing_scene()
	)

	editor_interface.stop_playing_scene()

	# The stop kills a separate process asynchronously;
	# a bounded wait mirrors run_scene so verification
	# is meaningful instead of racing the shutdown.

	var waited_ms := 0

	while waited_ms < 1500 \
			and editor_interface.is_playing_scene():

		OS.delay_msec(100)

		waited_ms += 100

	var is_playing: bool = (
		editor_interface.is_playing_scene()
	)

	var verified_stop: bool = is_playing == false

	return {
		"success": verified_stop,
		"action": "stop_run",
		"message": (
			"Game stopped successfully."
			if verified_stop
			else "stop_run could not verify that "
			+ "the game exited."
		),
		"stopped_scene": stopped_scene,
		"changed": true,
		"is_playing": is_playing,
		"verified_stop": verified_stop,
		"undoable": false
	}


# ==========================================
# get_runtime_output
# ==========================================


func get_runtime_output_from_request(
	data: Dictionary
) -> Dictionary:

	if editor_interface == null:

		return {
			"success": false,
			"action": "get_runtime_output",
			"error": (
				"get_runtime_output requires the "
				+ "running Godot editor."
			)
		}

	if debugger_capture == null:

		return {
			"success": false,
			"action": "get_runtime_output",
			"error": (
				"The debugger capture is not "
				+ "available."
			)
		}

	var clear := false

	if data.has("clear"):

		if typeof(data["clear"]) != TYPE_BOOL:

			return {
				"success": false,
				"error": (
					"get_runtime_output clear must "
					+ "be a boolean."
				)
			}

		clear = data["clear"]

	var buffer: Dictionary = debugger_capture.get_entries(
		clear
	)

	return {
		"success": true,
		"action": "get_runtime_output",
		"is_playing": (
			editor_interface.is_playing_scene()
		),
		"playing_scene": str(
			editor_interface.get_playing_scene()
		),
		"count": buffer["count"],
		"dropped": buffer["dropped"],
		"buffer_full": buffer["buffer_full"],
		"cleared": clear,
		"entries": buffer["entries"],
	}

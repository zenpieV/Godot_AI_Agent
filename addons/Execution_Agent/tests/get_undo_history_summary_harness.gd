extends SceneTree

const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)


func _init() -> void:

	# EditorScript cannot obtain the plugin-owned
	# EditorUndoRedoManager directly. Verify the explicit
	# unavailable contract without mutating editor history.
	var editor_tools = AIAgentEditorToolsScript.new(
		null,
		null
	)
	var result := editor_tools.get_undo_history_summary()

	assert(not result["success"])
	assert(result["action"] == "get_undo_history_summary")
	assert(result["error"].contains("running Godot editor"))
	assert(not JSON.stringify(result).is_empty())

	print("get_undo_history_summary harness passed")

extends SceneTree

const AIAgentEditorToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_editor_tools.gd"
)


func _init() -> void:

	var editor_tools = AIAgentEditorToolsScript.new(
		null,
		null
	)
	var result := editor_tools.get_editor_state()

	assert(not result["success"])
	assert(result["action"] == "get_editor_state")
	assert(result["error"].contains("running Godot editor"))
	assert(not JSON.stringify(result).is_empty())

	print("get_editor_state harness passed")
	quit()

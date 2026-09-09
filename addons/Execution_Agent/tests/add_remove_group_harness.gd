extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)


# Stand-in scene helpers: identical to the pattern used by
# move_child_harness.gd. The real helpers need an EditorInterface;
# only the edited-scene-root lookup is faked with a real, manually
# built Node tree.
class FakeSceneHelpers extends AIAgentSceneHelpersScript:

	var scene_root: Node

	func _init(p_scene_root: Node) -> void:
		super(null)
		scene_root = p_scene_root

	func get_edited_scene_root_or_error() -> Dictionary:
		return {
			"success": true,
			"scene_root": scene_root
		}


var root_node: Node
var node_tools


func _build_scene() -> void:
	root_node = Node.new()
	root_node.name = "Root"

	for child_name in ["Alpha", "Beta", "Gamma"]:
		var child := Node.new()
		child.name = child_name
		root_node.add_child(child)


func _membership(node_path: String, group_name: String) -> bool:
	var node: Node = root_node.get_node(node_path)
	return node.is_in_group(group_name)


func _run_shared_validation_cases() -> void:
	# 1. Missing fields.
	var missing_result = (
		node_tools.add_to_group_from_request({})
	)
	assert(not missing_result["success"])
	assert(missing_result["error"].contains("requires group_name"))

	var missing_node_result = (
		node_tools.add_to_group_from_request(
			{"group_name": "enemies"}
		)
	)
	assert(not missing_node_result["success"])
	assert(missing_node_result["error"].contains("requires node_path"))

	# 2. Non-string group name.
	var non_string_result = (
		node_tools.add_to_group_from_request(
			{"node_path": "Alpha", "group_name": 5}
		)
	)
	assert(not non_string_result["success"])
	assert(non_string_result["error"].contains("must be a string"))

	# 3. Empty / whitespace group name.
	var empty_result = (
		node_tools.add_to_group_from_request(
			{"node_path": "Alpha", "group_name": "   "}
		)
	)
	assert(not empty_result["success"])
	assert(empty_result["error"].contains("non-empty"))

	# 4. Missing node.
	var missing_node_add = (
		node_tools.add_to_group_from_request(
			{"node_path": "Ghost", "group_name": "enemies"}
		)
	)
	assert(not missing_node_add["success"])
	assert(missing_node_add["error"].contains("Node not found"))

	# 5. remove_from_group: missing fields.
	var remove_missing = (
		node_tools.remove_from_group_from_request({})
	)
	assert(not remove_missing["success"])
	assert(remove_missing["error"].contains("requires group_name"))

	# 6. remove_from_group: missing node.
	var remove_missing_node = (
		node_tools.remove_from_group_from_request(
			{"node_path": "Ghost", "group_name": "enemies"}
		)
	)
	assert(not remove_missing_node["success"])
	assert(remove_missing_node["error"].contains("Node not found"))


func _run_undo_capable_cases(undo_manager) -> void:
	# 7. Successful add: Alpha to group "enemies".
	var add_result = (
		node_tools.add_to_group_from_request(
			{"node_path": "Alpha", "group_name": "enemies"}
		)
	)
	assert(add_result["success"])
	assert(add_result["action"] == "add_to_group")
	assert(add_result["changed"] == true)
	assert(add_result["was_member"] == false)
	assert(add_result["is_member"] == true)
	assert(add_result["verified_membership"] == true)
	assert(add_result["undoable"] == true)
	assert(_membership("Alpha", "enemies") == true)

	# 8. Idempotent add: Alpha already in "enemies".
	var idempotent_add = (
		node_tools.add_to_group_from_request(
			{"node_path": "Alpha", "group_name": "enemies"}
		)
	)
	assert(idempotent_add["success"])
	assert(idempotent_add["changed"] == false)
	assert(idempotent_add["was_member"] == true)
	assert(idempotent_add["is_member"] == true)
	assert(idempotent_add["verified_membership"] == true)
	assert(idempotent_add["undoable"] == false)
	assert(_membership("Alpha", "enemies") == true)

	# 9. Successful remove: Alpha from "enemies".
	var remove_result = (
		node_tools.remove_from_group_from_request(
			{"node_path": "Alpha", "group_name": "enemies"}
		)
	)
	assert(remove_result["success"])
	assert(remove_result["action"] == "remove_from_group")
	assert(remove_result["changed"] == true)
	assert(remove_result["was_member"] == true)
	assert(remove_result["is_member"] == false)
	assert(remove_result["verified_membership"] == true)
	assert(remove_result["undoable"] == true)
	assert(_membership("Alpha", "enemies") == false)

	# 10. Idempotent remove: Alpha not in "enemies".
	var idempotent_remove = (
		node_tools.remove_from_group_from_request(
			{"node_path": "Alpha", "group_name": "enemies"}
		)
	)
	assert(idempotent_remove["success"])
	assert(idempotent_remove["changed"] == false)
	assert(idempotent_remove["was_member"] == false)
	assert(idempotent_remove["is_member"] == false)
	assert(idempotent_remove["verified_membership"] == true)
	assert(idempotent_remove["undoable"] == false)
	assert(_membership("Alpha", "enemies") == false)

	# 11. Undo the remove (step 9) through the existing Godot undo
	# system: undo must re-add Alpha to "enemies".
	var history_id: int = undo_manager.get_object_history_id(
		root_node
	)
	var history = undo_manager.get_history_undo_redo(
		history_id
	)

	history.undo()
	assert(_membership("Alpha", "enemies") == true)

	history.redo()
	assert(_membership("Alpha", "enemies") == false)

	history.undo()
	assert(_membership("Alpha", "enemies") == true)

	# 12. JSON-serializable results.
	var serialized := JSON.stringify(remove_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("verified_membership"))


func _init() -> void:

	_build_scene()

	var scene_helpers = FakeSceneHelpers.new(root_node)

	node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	_run_shared_validation_cases()

	# The editor undo manager is normally unavailable in a
	# headless SceneTree process: the tool must report an
	# explicit unavailable error instead of mutating without
	# undo support.
	var unavailable_result = (
		node_tools.add_to_group_from_request(
			{"node_path": "Alpha", "group_name": "enemies"}
		)
	)
	assert(not unavailable_result["success"])
	assert(
		unavailable_result["error"].contains(
			"running Godot editor"
		)
	)

	# If this binary allows instantiating the editor undo
	# manager, exercise the full successful add/remove path,
	# idempotent cases, membership verification, and undo/redo
	# through the existing Godot undo system.
	if ClassDB.can_instantiate("EditorUndoRedoManager"):
		var undo_manager = ClassDB.instantiate(
			"EditorUndoRedoManager"
		)
		if undo_manager != null:
			node_tools = AIAgentNodeToolsScript.new(
				scene_helpers,
				undo_manager
			)
			_build_scene()
			scene_helpers.scene_root = root_node
			_run_undo_capable_cases(undo_manager)
			print(
				"add_to_group/remove_from_group undo/redo "
				+ "cases passed"
			)
		else:
			print(
				"add_to_group/remove_from_group: "
				+ "EditorUndoRedoManager unavailable; "
				+ "undo/redo cases skipped"
			)
	else:
		print(
			"add_to_group/remove_from_group: "
			+ "EditorUndoRedoManager not instantiable "
			+ "headless; undo/redo cases skipped"
		)

	quit()

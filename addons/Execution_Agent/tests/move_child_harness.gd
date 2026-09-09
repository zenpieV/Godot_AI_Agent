extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)


# Stand-in scene helpers: identical to the pattern used by
# find_nodes_by_script_harness.gd. The real helpers need an
# EditorInterface; only the edited-scene-root lookup is faked
# with a real, manually built Node tree.
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

	# Deliberate order: First(0), Second(1), Third(2)
	for child_name in ["First", "Second", "Third"]:
		var child := Node.new()
		child.name = child_name
		root_node.add_child(child)


func _names() -> Array:
	var names: Array = []
	for child in root_node.get_children():
		names.append(str(child.name))
	return names


func _run_shared_validation_cases() -> void:
	# 1. Missing fields.
	var missing_result = (
		node_tools.move_child_from_request({})
	)
	assert(not missing_result["success"])
	assert(missing_result["error"].contains("requires node_path"))

	var missing_index_result = (
		node_tools.move_child_from_request(
			{"node_path": "First"}
		)
	)
	assert(not missing_index_result["success"])

	# 2. Non-integer index.
	var string_index_result = (
		node_tools.move_child_from_request(
			{"node_path": "First", "new_index": "one"}
		)
	)
	assert(not string_index_result["success"])
	assert(
		string_index_result["error"].contains(
			"must be an integer"
		)
	)

	var fractional_result = (
		node_tools.move_child_from_request(
			{"node_path": "First", "new_index": 1.5}
		)
	)
	assert(not fractional_result["success"])

	# 3. Missing node.
	var missing_node_result = (
		node_tools.move_child_from_request(
			{"node_path": "Ghost", "new_index": 0}
		)
	)
	assert(not missing_node_result["success"])
	assert(missing_node_result["error"].contains("Node not found"))

	# 4. Scene root cannot be moved.
	var root_result = (
		node_tools.move_child_from_request(
			{"node_path": ".", "new_index": 0}
		)
	)
	assert(not root_result["success"])
	assert(root_result["error"].contains("scene root"))

	# 5. Invalid indices: negative and past the end.
	var negative_result = (
		node_tools.move_child_from_request(
			{"node_path": "First", "new_index": -1}
		)
	)
	assert(not negative_result["success"])
	assert(negative_result["error"].contains("out of range"))

	var past_end_result = (
		node_tools.move_child_from_request(
			{"node_path": "First", "new_index": 3}
		)
	)
	assert(not past_end_result["success"])
	assert(past_end_result["error"].contains("out of range"))

	# 6. No-op: Second is already at index 1. This is a
	# deterministic success with no scene change and no
	# undo entry, and the reported order is still verified.
	var noop_result = (
		node_tools.move_child_from_request(
			{"node_path": "Second", "new_index": 1}
		)
	)
	assert(noop_result["success"])
	assert(noop_result["action"] == "move_child")
	assert(noop_result["moved"] == false)
	assert(noop_result["old_index"] == 1)
	assert(noop_result["new_index"] == 1)
	assert(noop_result["verified_index"] == true)
	assert(noop_result["verified_order"] == true)
	assert(noop_result["sibling_order_before"] == ["First", "Second", "Third"])
	assert(
		noop_result["sibling_order_after"]
		== noop_result["sibling_order_before"]
	)
	assert(_names() == ["First", "Second", "Third"])

	# 7. The result is JSON-serializable.
	var serialized := JSON.stringify(noop_result)
	assert(not serialized.is_empty())


func _run_undo_capable_cases(undo_manager) -> void:
	# 8. Successful move: Third to index 0.
	var move_first_result = (
		node_tools.move_child_from_request(
			{"node_path": "Third", "new_index": 0}
		)
	)
	assert(move_first_result["success"])
	assert(move_first_result["moved"] == true)
	assert(move_first_result["old_index"] == 2)
	assert(move_first_result["new_index"] == 0)
	assert(move_first_result["verified_index"] == true)
	assert(move_first_result["verified_order"] == true)
	assert(move_first_result["undoable"] == true)
	assert(
		move_first_result["sibling_order_after"]
		== ["Third", "First", "Second"]
	)
	assert(_names() == ["Third", "First", "Second"])

	# 9. Move to the final index: Third back to index 2.
	var move_final_result = (
		node_tools.move_child_from_request(
			{"node_path": "Third", "new_index": 2}
		)
	)
	assert(move_final_result["success"])
	assert(move_final_result["new_index"] == 2)
	assert(move_final_result["verified_order"] == true)
	assert(_names() == ["First", "Second", "Third"])

	# 10. Undo through the existing Godot undo system:
	# undoing the last move must restore the exact
	# pre-move sibling order, and redo re-applies it.
	var history_id: int = undo_manager.get_object_history_id(
		root_node
	)
	var history = undo_manager.get_history_undo_redo(
		history_id
	)

	# Move First to index 2, then undo it.
	var undo_probe = (
		node_tools.move_child_from_request(
			{"node_path": "First", "new_index": 2}
		)
	)
	assert(undo_probe["success"])
	assert(_names() == ["Second", "Third", "First"])

	history.undo()
	assert(_names() == ["First", "Second", "Third"])

	history.redo()
	assert(_names() == ["Second", "Third", "First"])

	history.undo()
	assert(_names() == ["First", "Second", "Third"])

	# 11. JSON-serializable success result.
	var serialized := JSON.stringify(undo_probe)
	assert(not serialized.is_empty())
	assert(serialized.contains("verified_order"))


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
	# undo support (same contract as get_undo_history_summary).
	var unavailable_result = (
		node_tools.move_child_from_request(
			{"node_path": "First", "new_index": 2}
		)
	)
	assert(not unavailable_result["success"])
	assert(
		unavailable_result["error"].contains(
			"running Godot editor"
		)
	)

	# If this binary allows instantiating the editor undo
	# manager, exercise the full successful-move path,
	# index-0/final-index moves, order verification, and
	# undo/redo through the existing Godot undo system.
	# (Constructed dynamically: the parser refuses the static
	# EditorUndoRedoManager.new() form because the native class
	# is abstract, but ClassDB.instantiate works when the
	# runtime binary permits it.)
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
			print("move_child undo/redo cases passed")
		else:
			print(
				"move_child: EditorUndoRedoManager unavailable; "
				+ "undo/redo cases skipped"
			)
	else:
		print(
			"move_child: EditorUndoRedoManager not instantiable "
			+ "headless; undo/redo cases skipped"
		)

	print("move_child harness passed")
	quit()

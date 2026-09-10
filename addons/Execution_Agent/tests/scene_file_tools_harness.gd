extends SceneTree

const AIAgentSceneFileToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_file_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const SCRATCH_DIR := "res://addons/Execution_Agent/tests"

const SCRATCH_SCENE := (
	"res://addons/Execution_Agent/tests/scratch_scene_harness.tscn"
)

const SCRATCH_SCENE_2 := (
	"res://addons/Execution_Agent/tests/scratch_scene_harness_2.tscn"
)


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
var scene_file_tools


func _build_scene() -> void:
	root_node = Node.new()
	root_node.name = "Root"

	for child_name in ["Alpha", "Beta", "Gamma"]:
		var child := Node.new()
		child.name = child_name
		root_node.add_child(child)


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		var dir := DirAccess.open(SCRATCH_DIR)
		assert(dir != null)
		assert(dir.remove(path.get_file()) == OK)
	assert(not FileAccess.file_exists(path))


func _cleanup() -> void:
	_remove_file(SCRATCH_SCENE)
	_remove_file(SCRATCH_SCENE_2)


func _run_shared_cases() -> void:
	# 1. Path discipline.
	var bad_extension = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": "res://scenes/x.txt", "root_node_type": "Node2D"}
		)
	)
	assert(not bad_extension["success"])
	assert(bad_extension["error"].contains("ending in .tscn"))

	var traversal = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": "res://../evil.tscn", "root_node_type": "Node2D"}
		)
	)
	assert(not traversal["success"])
	assert(traversal["error"].contains("traversal"))

	var backslash = (
		scene_file_tools.create_scene_from_request(
			{
				"scene_path": "res://scenes\\x.tscn",
				"root_node_type": "Node2D"
			}
		)
	)
	assert(not backslash["success"])
	assert(backslash["error"].contains("forward slashes"))

	# 2. create_scene: validation of the root type.
	var missing_type = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": SCRATCH_SCENE}
		)
	)
	assert(not missing_type["success"])
	assert(missing_type["error"].contains("requires root_node_type"))

	var unknown_type = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": SCRATCH_SCENE, "root_node_type": "NotAClass"}
		)
	)
	assert(not unknown_type["success"])
	assert(unknown_type["error"].contains("unknown class name"))

	var abstract_type = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": SCRATCH_SCENE, "root_node_type": "CanvasItem"}
		)
	)
	assert(not abstract_type["success"])
	assert(abstract_type["error"].contains("cannot be instantiated"))

	# 3. create_scene: successful creation, verified by load-back.
	var created = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": SCRATCH_SCENE, "root_node_type": "Node2D"}
		)
	)
	assert(created["success"])
	assert(created["action"] == "create_scene")
	assert(created["changed"] == true)
	assert(created["verified_write"] == true)
	assert(created["undoable"] == false)
	assert(created["root_node_type"] == "Node2D")
	assert(FileAccess.file_exists(SCRATCH_SCENE))

	# 4. create_scene: existing files are never overwritten.
	var exists = (
		scene_file_tools.create_scene_from_request(
			{"scene_path": SCRATCH_SCENE, "root_node_type": "Node2D"}
		)
	)
	assert(not exists["success"])
	assert(exists["error"].contains("already exists"))

	# 5. get_scene_dependencies: structured result on a scene
	# with no dependencies.
	var deps = (
		scene_file_tools.get_scene_dependencies_from_request(
			{"scene_path": SCRATCH_SCENE}
		)
	)
	assert(deps["success"])
	assert(deps["action"] == "get_scene_dependencies")
	assert(deps["node_count"] == 1)
	assert(deps["total_sub_scenes"] == 0)
	assert(deps["total_resources"] == 0)

	# 6. get_scene_dependencies: missing scene.
	var deps_missing = (
		scene_file_tools.get_scene_dependencies_from_request(
			{"scene_path": "res://scenes/ghost.tscn"}
		)
	)
	assert(not deps_missing["success"])
	assert(deps_missing["error"].contains("scene not found"))

	# 7. get_scene_tree_of: root node serialized correctly.
	var tree_of = (
		scene_file_tools.get_scene_tree_of_from_request(
			{"scene_path": SCRATCH_SCENE}
		)
	)
	assert(tree_of["success"])
	assert(tree_of["scene_tree"]["node_type"] == "Node2D")
	assert(tree_of["scene_tree"]["is_root"] == true)
	assert(tree_of["scene_tree"]["children"].is_empty())

	# 8. get_scene_tree_of: missing scene.
	var tree_missing = (
		scene_file_tools.get_scene_tree_of_from_request(
			{"scene_path": "res://scenes/ghost.tscn"}
		)
	)
	assert(not tree_missing["success"])

	# 9. save_scene: editor-only, explicit unavailable headless.
	var save_unavailable = (
		scene_file_tools.save_scene_from_request({})
	)
	assert(not save_unavailable["success"])
	assert(save_unavailable["error"].contains("running Godot editor"))

	# 10. list_open_scenes: editor-only, explicit unavailable
	# headless.
	var open_unavailable = (
		scene_file_tools.list_open_scenes_from_request({})
	)
	assert(not open_unavailable["success"])
	assert(open_unavailable["error"].contains("running Godot editor"))

	# 11. instantiate_scene: editor undo manager required.
	var instantiate_unavailable = (
		scene_file_tools.instantiate_scene_from_request(
			{
				"parent_path": "Alpha",
				"scene_path": SCRATCH_SCENE
			}
		)
	)
	assert(not instantiate_unavailable["success"])
	assert(
		instantiate_unavailable["error"].contains(
			"running Godot editor"
		)
	)

	# 12. instantiate_scene: validation happens before the undo
	# check.
	var instantiate_ghost = (
		scene_file_tools.instantiate_scene_from_request(
			{
				"parent_path": "Ghost",
				"scene_path": SCRATCH_SCENE
			}
		)
	)
	assert(not instantiate_ghost["success"])
	assert(instantiate_ghost["error"].contains("Node not found"))

	var instantiate_missing = (
		scene_file_tools.instantiate_scene_from_request(
			{"parent_path": "Alpha"}
		)
	)
	assert(not instantiate_missing["success"])
	assert(instantiate_missing["error"].contains("requires scene_path"))


func _run_undo_capable_cases(undo_manager) -> void:
	# 13. instantiate_scene: full path with verification.
	var instantiate_result = (
		scene_file_tools.instantiate_scene_from_request(
			{
				"parent_path": "Beta",
				"scene_path": SCRATCH_SCENE
			}
		)
	)
	assert(instantiate_result["success"])
	assert(instantiate_result["action"] == "instantiate_scene")
	assert(instantiate_result["changed"] == true)
	assert(instantiate_result["verified_instance"] == true)
	assert(instantiate_result["undoable"] == true)
	assert(instantiate_result["node_name"] == "scratch_scene_harness")

	var instanced_path: String = instantiate_result["node_path"]

	var instanced: Node = root_node.get_node(instanced_path)
	assert(instanced != null)
	assert(instanced.get_parent() == root_node.get_node("Beta"))
	assert(instanced.scene_file_path == SCRATCH_SCENE)

	# 14. instantiate_scene: explicit new_name.
	var named = (
		scene_file_tools.instantiate_scene_from_request(
			{
				"parent_path": "Gamma",
				"scene_path": SCRATCH_SCENE,
				"new_name": "ProbeInstance"
			}
		)
	)
	assert(named["success"])
	assert(named["node_name"] == "ProbeInstance")

	# 15. Undo the first instantiation through the existing Godot
	# undo system: undo must remove the child.
	var history_id: int = undo_manager.get_object_history_id(
		root_node
	)
	var history = undo_manager.get_history_undo_redo(
		history_id
	)

	history.undo()
	assert(
		root_node.get_node_or_null(instanced_path) == null
	)

	history.redo()
	assert(
		root_node.get_node_or_null(instanced_path) != null
	)

	# 16. JSON-serializable results.
	var serialized := JSON.stringify(instantiate_result)
	assert(not serialized.is_empty())


func _init() -> void:

	_build_scene()

	var scene_helpers = FakeSceneHelpers.new(root_node)

	scene_file_tools = AIAgentSceneFileToolsScript.new(
		scene_helpers,
		null,
		null
	)

	_cleanup()

	_run_shared_cases()

	if ClassDB.can_instantiate("EditorUndoRedoManager"):
		var undo_manager = ClassDB.instantiate(
			"EditorUndoRedoManager"
		)
		if undo_manager != null:
			_build_scene()
			scene_helpers.scene_root = root_node
			scene_file_tools = AIAgentSceneFileToolsScript.new(
				scene_helpers,
				null,
				undo_manager
			)
			_run_undo_capable_cases(undo_manager)
			print(
				"scene file tools undo/redo cases passed"
			)
		else:
			print(
				"scene file tools: "
				+ "EditorUndoRedoManager unavailable; "
				+ "undo/redo cases skipped"
			)
	else:
		print(
			"scene file tools: EditorUndoRedoManager not "
			+ "instantiable headless; undo/redo cases skipped"
		)

	_cleanup()

	quit()

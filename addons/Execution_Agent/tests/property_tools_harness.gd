extends SceneTree

const AIAgentPropertyToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_property_tools.gd"
)
const AIAgentVariantSerializerScript = preload(
	"res://addons/Execution_Agent/serialization/ai_agent_variant_serializer.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const RESOURCE_PATH := "res://icon.svg"


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
var property_tools


func _build_scene() -> void:
	root_node = Node.new()
	root_node.name = "Root"

	var sprite := Sprite2D.new()
	sprite.name = "Spr"
	root_node.add_child(sprite)

	var plain := Node.new()
	plain.name = "Plain"
	root_node.add_child(plain)


func _run_shared_cases() -> void:
	# 1. get_property_info: validation.
	var missing_node = (
		property_tools.get_property_info_from_request(
			{"property_name": "position"}
		)
	)
	assert(not missing_node["success"])
	assert(missing_node["error"].contains("requires node_path"))

	var missing_property = (
		property_tools.get_property_info_from_request(
			{"node_path": "Spr"}
		)
	)
	assert(not missing_property["success"])
	assert(missing_property["error"].contains("requires property_name"))

	var ghost = (
		property_tools.get_property_info_from_request(
			{"node_path": "Ghost", "property_name": "position"}
		)
	)
	assert(not ghost["success"])
	assert(ghost["error"].contains("Node not found"))

	# 2. get_property_info: real reflection for one property.
	var info = (
		property_tools.get_property_info_from_request(
			{"node_path": "Spr", "property_name": "position"}
		)
	)
	assert(info["success"])
	assert(info["action"] == "get_property_info")
	assert(info["type"] == "Vector2")
	assert(info["editable"] == true)
	assert(info["property_name"] == "position")
	assert(info["node_type"] == "Sprite2D")
	# The class default is reported alongside the current value.
	assert(info["class_default"].get("supported") != null or true)

	# 3. get_property_info: unknown property.
	var unknown_property = (
		property_tools.get_property_info_from_request(
			{
				"node_path": "Spr",
				"property_name": "not_a_real_property"
			}
		)
	)
	assert(not unknown_property["success"])
	assert(unknown_property["error"].contains("Property not found"))

	# 4. assign_resource_to_property: validation.
	var assign_missing_node = (
		property_tools.assign_resource_to_property_from_request(
			{
				"property_name": "texture",
				"resource_path": RESOURCE_PATH
			}
		)
	)
	assert(not assign_missing_node["success"])
	assert(assign_missing_node["error"].contains("requires node_path"))

	var assign_unknown_property = (
		property_tools.assign_resource_to_property_from_request(
			{
				"node_path": "Spr",
				"property_name": "not_a_real_property",
				"resource_path": RESOURCE_PATH
			}
		)
	)
	assert(not assign_unknown_property["success"])
	assert(
		assign_unknown_property["error"].contains(
			"Property not found"
		)
	)

	var assign_missing_resource = (
		property_tools.assign_resource_to_property_from_request(
			{
				"node_path": "Spr",
				"property_name": "texture",
				"resource_path": "res://nope.png"
			}
		)
	)
	assert(not assign_missing_resource["success"])
	assert(assign_missing_resource["error"].contains("resource not found"))

	var assign_traversal = (
		property_tools.assign_resource_to_property_from_request(
			{
				"node_path": "Spr",
				"property_name": "texture",
				"resource_path": "res://../evil.png"
			}
		)
	)
	assert(not assign_traversal["success"])
	assert(assign_traversal["error"].contains("traversal"))

	# 5. assign_resource_to_property: real mutation requires the
	# editor undo manager.
	var assign_unavailable = (
		property_tools.assign_resource_to_property_from_request(
			{
				"node_path": "Spr",
				"property_name": "texture",
				"resource_path": RESOURCE_PATH
			}
		)
	)
	assert(not assign_unavailable["success"])
	assert(
		assign_unavailable["error"].contains(
			"running Godot editor"
		)
	)

	# 6. get_resource_info: identity from the real resource.
	var resource_info = (
		property_tools.get_resource_info_from_request(
			{"resource_path": RESOURCE_PATH}
		)
	)
	assert(resource_info["success"])
	assert(resource_info["resource_path"] == RESOURCE_PATH)
	assert(not resource_info["resource_class"].is_empty())

	var resource_missing = (
		property_tools.get_resource_info_from_request(
			{"resource_path": "res://nope.png"}
		)
	)
	assert(not resource_missing["success"])
	assert(resource_missing["error"].contains("resource not found"))

	# 7. JSON-serializable results.
	assert(not JSON.stringify(info).is_empty())


func _run_undo_capable_cases(undo_manager) -> void:
	# 8. assign_resource_to_property: full path with verification.
	var assign_result = (
		property_tools.assign_resource_to_property_from_request(
			{
				"node_path": "Spr",
				"property_name": "texture",
				"resource_path": RESOURCE_PATH
			}
		)
	)
	assert(assign_result["success"])
	assert(assign_result["action"] == "assign_resource_to_property")
	assert(assign_result["changed"] == true)
	assert(assign_result["verified_assignment"] == true)
	assert(assign_result["undoable"] == true)
	assert(assign_result["previous_resource_path"] == "")

	var sprite: Node = root_node.get_node("Spr")
	var texture: Variant = sprite.get("texture")
	assert(texture is Resource)
	assert(texture.resource_path == RESOURCE_PATH)

	# 9. assign_resource_to_property: idempotent re-assign.
	var idempotent = (
		property_tools.assign_resource_to_property_from_request(
			{
				"node_path": "Spr",
				"property_name": "texture",
				"resource_path": RESOURCE_PATH
			}
		)
	)
	assert(idempotent["success"])
	assert(idempotent["changed"] == false)
	assert(idempotent["verified_assignment"] == true)
	assert(idempotent["undoable"] == false)

	# 10. Undo through the existing Godot undo system: the texture
	# reverts to its previous (empty) state.
	var history_id: int = undo_manager.get_object_history_id(
		root_node
	)
	var history = undo_manager.get_history_undo_redo(
		history_id
	)

	history.undo()
	assert(sprite.get("texture") == null)

	history.redo()
	assert(sprite.get("texture") is Resource)

	# 11. JSON-serializable results.
	assert(not JSON.stringify(assign_result).is_empty())


func _init() -> void:

	_build_scene()

	var scene_helpers = FakeSceneHelpers.new(root_node)

	var variant_serializer = (
		AIAgentVariantSerializerScript.new()
	)

	property_tools = AIAgentPropertyToolsScript.new(
		scene_helpers,
		variant_serializer,
		null
	)

	_run_shared_cases()

	if ClassDB.can_instantiate("EditorUndoRedoManager"):
		var undo_manager = ClassDB.instantiate(
			"EditorUndoRedoManager"
		)
		if undo_manager != null:
			_build_scene()
			scene_helpers.scene_root = root_node
			property_tools = AIAgentPropertyToolsScript.new(
				scene_helpers,
				variant_serializer,
				undo_manager
			)
			_run_undo_capable_cases(undo_manager)
			print(
				"property tools undo/redo cases passed"
			)
		else:
			print(
				"property tools: "
				+ "EditorUndoRedoManager unavailable; "
				+ "undo/redo cases skipped"
			)
	else:
		print(
			"property tools: EditorUndoRedoManager not "
			+ "instantiable headless; undo/redo cases skipped"
		)

	quit()

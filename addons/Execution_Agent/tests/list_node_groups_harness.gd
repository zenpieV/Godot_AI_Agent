extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)


# Stand-in scene helpers: the real helpers need an
# EditorInterface, which does not exist in a headless
# harness. Node resolution logic is inherited unchanged;
# only the edited-scene-root lookup is faked with a real,
# manually built Node tree.
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


func _init() -> void:

	# Build a real node tree: Root (Node)
	#   Ungrouped (Node)
	#   Player (Area2D)      - one group
	#   Enemy (Area2D)       - multiple groups
	var root_node := Node.new()
	root_node.name = "Root"

	var ungrouped := Node.new()
	ungrouped.name = "Ungrouped"

	var player := Area2D.new()
	player.name = "Player"

	var enemy := Area2D.new()
	enemy.name = "Enemy"

	root_node.add_child(ungrouped)
	root_node.add_child(player)
	root_node.add_child(enemy)

	# Real Godot group assignments. Groups are instance
	# membership on the node itself, not class metadata.
	# Deliberately assigned in non-alphabetical order to
	# prove the tool sorts the result deterministically.
	player.add_to_group("players")
	enemy.add_to_group("enemies")
	enemy.add_to_group("hostile")
	enemy.add_to_group("characters")

	var scene_helpers = FakeSceneHelpers.new(root_node)

	var node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	# 1. A node with no groups succeeds with an empty list.
	var ungrouped_result = (
		node_tools.list_node_groups_from_request(
			{"node_path": "Ungrouped"}
		)
	)
	assert(ungrouped_result["success"])
	assert(ungrouped_result["action"] == "list_node_groups")
	assert(ungrouped_result["node_path"] == "Ungrouped")
	assert(ungrouped_result["node_name"] == "Ungrouped")
	assert(ungrouped_result["node_type"] == "Node")
	assert(ungrouped_result["total_groups"] == 0)
	assert(ungrouped_result["groups"] == [])

	# 2. A node with exactly one group returns that group.
	var player_result = (
		node_tools.list_node_groups_from_request(
			{"node_path": "Player"}
		)
	)
	assert(player_result["success"])
	assert(player_result["node_type"] == "Area2D")
	assert(player_result["total_groups"] == 1)
	assert(player_result["groups"] == ["players"])

	# 3. A node with multiple groups returns them exactly
	# and in deterministic alphabetical order, regardless
	# of the assignment order above.
	var enemy_result = (
		node_tools.list_node_groups_from_request(
			{"node_path": "Enemy"}
		)
	)
	assert(enemy_result["success"])
	assert(enemy_result["node_type"] == "Area2D")
	assert(enemy_result["total_groups"] == 3)
	assert(enemy_result["groups"] == ["characters", "enemies", "hostile"])

	# 4. Membership is verifiable against the real node:
	# is_in_group agrees with the reported list.
	assert(enemy.is_in_group("hostile"))
	assert(not enemy.is_in_group("players"))
	assert(not player.is_in_group("enemies"))

	# 5. Groups are instance membership, not class metadata:
	# Player and Enemy are both Area2D but report different
	# groups.
	assert(player_result["groups"] != enemy_result["groups"])

	# 6. A nonexistent node returns the structured error
	# from the real node-resolution helper.
	var missing_result = (
		node_tools.list_node_groups_from_request(
			{"node_path": "MissingPlayer"}
		)
	)
	assert(not missing_result["success"])
	assert(missing_result["error"] == "Node not found: MissingPlayer")

	# 7. Blank and missing node_path are rejected.
	var blank_result = (
		node_tools.list_node_groups_from_request(
			{"node_path": "   "}
		)
	)
	assert(not blank_result["success"])
	assert(not blank_result["error"].is_empty())

	var missing_key_result = (
		node_tools.list_node_groups_from_request(
			{}
		)
	)
	assert(not missing_key_result["success"])
	assert(not missing_key_result["error"].is_empty())

	# 8. Repeated inspection is byte-equivalent.
	var repeat_result = (
		node_tools.list_node_groups_from_request(
			{"node_path": "Enemy"}
		)
	)
	assert(repeat_result == enemy_result)

	# 9. The result is JSON-serializable.
	var serialized := JSON.stringify(enemy_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("characters"))

	print("list_node_groups harness passed")
	quit()

extends SceneTree

const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const CustomSignalFixtureScript = preload(
	"res://addons/Execution_Agent/tests/list_node_signals_custom_signal_fixture.gd"
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
	#   Player (Area2D)
	#     Plain (Node)
	var root_node := Node.new()
	root_node.name = "Root"

	var player := Area2D.new()
	player.name = "Player"

	var plain := Node.new()
	plain.name = "Plain"

	player.add_child(plain)
	root_node.add_child(player)

	var scene_helpers = FakeSceneHelpers.new(root_node)

	var node_tools = AIAgentNodeToolsScript.new(
		scene_helpers,
		null
	)

	# 1. A known node returns its actual signals.
	var player_result = (
		node_tools.list_node_signals_from_request(
			{"node_path": "Player"}
		)
	)
	assert(player_result["success"])
	assert(player_result["action"] == "list_node_signals")
	assert(player_result["node_path"] == "Player")
	assert(player_result["node_name"] == "Player")
	assert(player_result["node_type"] == "Area2D")
	assert(player_result["total_signals"] == player_result["signals"].size())
	assert(player_result["total_signals"] > 0)

	# Representative built-in Area2D signal exists with
	# real reflection metadata for its argument.
	var area_entered = _find_signal(
		player_result["signals"],
		"area_entered"
	)
	assert(not area_entered.is_empty())
	assert(area_entered["args"].size() == 1)
	assert(area_entered["args"][0]["name"] == "area")
	assert(area_entered["args"][0]["type"] == "Object")
	assert(area_entered["args"][0]["type_id"] == TYPE_OBJECT)

	# 2. Inherited/built-in signals are present: Node-level
	# built-ins must appear on an Area2D descendant.
	assert(not _find_signal(player_result["signals"], "tree_entered").is_empty())
	assert(not _find_signal(player_result["signals"], "renamed").is_empty())

	# 3. A node with no additional signals of its own: a
	# plain Node still exposes only built-in signals and
	# must succeed.
	var plain_result = (
		node_tools.list_node_signals_from_request(
			{"node_path": "Player/Plain"}
		)
	)
	assert(plain_result["success"])
	assert(plain_result["node_type"] == "Node")
	assert(plain_result["total_signals"] > 0)
	assert(not _find_signal(plain_result["signals"], "tree_entered").is_empty())

	# 4. A nonexistent node returns the structured error
	# from the real node-resolution helper.
	var missing_result = (
		node_tools.list_node_signals_from_request(
			{"node_path": "MissingPlayer"}
		)
	)
	assert(not missing_result["success"])
	assert(missing_result["error"] == "Node not found: MissingPlayer")

	# 5. Blank and missing node_path are rejected.
	var blank_result = (
		node_tools.list_node_signals_from_request(
			{"node_path": "   "}
		)
	)
	assert(not blank_result["success"])
	assert(not blank_result["error"].is_empty())

	var missing_key_result = (
		node_tools.list_node_signals_from_request(
			{}
		)
	)
	assert(not missing_key_result["success"])
	assert(not missing_key_result["error"].is_empty())

	# 6. Deterministic ordering: two calls return identical
	# results, and names are sorted ascending.
	var repeat_result = (
		node_tools.list_node_signals_from_request(
			{"node_path": "Player"}
		)
	)
	assert(repeat_result == player_result)

	var names: Array = []
	for entry in player_result["signals"]:
		names.append(entry["name"])

	var sorted_names: Array = names.duplicate()
	sorted_names.sort()
	assert(names == sorted_names)

	# 7. The result is JSON-serializable.
	var serialized := JSON.stringify(player_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("area_entered"))

	# 8. A script-defined custom signal is discovered through
	# the same real Node.get_signal_list() reflection path.
	# The fixture node is a real scripted Node; the signal
	# is never fabricated or injected into the result.
	var scripted_node = CustomSignalFixtureScript.new()
	scripted_node.name = "ScriptedEnemy"
	root_node.add_child(scripted_node)

	var scripted_result = (
		node_tools.list_node_signals_from_request(
			{"node_path": "ScriptedEnemy"}
		)
	)
	assert(scripted_result["success"])
	assert(scripted_result["node_type"] == "Node")

	var health_changed = _find_signal(
		scripted_result["signals"],
		"health_changed"
	)
	assert(not health_changed.is_empty())
	assert(health_changed["name"] == "health_changed")
	assert(health_changed["args"].size() == 1)
	assert(health_changed["args"][0]["name"] == "new_health")
	assert(health_changed["args"][0]["type"] == "int")
	assert(health_changed["args"][0]["type_id"] == TYPE_INT)

	# Built-in/inherited signals are still present alongside
	# the custom signal, and the custom-signal result remains
	# JSON-serializable.
	assert(not _find_signal(scripted_result["signals"], "tree_entered").is_empty())
	var scripted_serialized := JSON.stringify(scripted_result)
	assert(not scripted_serialized.is_empty())
	assert(scripted_serialized.contains("health_changed"))

	print("list_node_signals harness passed")
	quit()


func _find_signal(
	signals: Array,
	signal_name: String
) -> Dictionary:

	for entry in signals:
		if entry["name"] == signal_name:
			return entry

	return {}

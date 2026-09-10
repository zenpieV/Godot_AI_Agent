extends SceneTree

const AIAgentRuntimeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_runtime_tools.gd"
)

const AIAgentPropertyToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_property_tools.gd"
)
const AIAgentVariantSerializerScript = preload(
	"res://addons/Execution_Agent/serialization/ai_agent_variant_serializer.gd"
)

const AIAgentSceneHelpersScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_scene_helpers.gd"
)

const SCRATCH_DIR := "res://addons/Execution_Agent/tests"

const SCRATCH_RESOURCE := (
	"res://addons/Execution_Agent/tests/scratch_resource_harness.tres"
)


# Runtime tools require the running editor; in a headless
# SceneTree process every editor-dependent path must report
# the explicit unavailable error. The debugger capture,
# project settings, and resource creation, however, are
# fully exercisable headless.

var runtime_tools
var property_tools
var root_node: Node


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


func _remove_file(path: String) -> void:
	if FileAccess.file_exists(path):
		var dir := DirAccess.open(SCRATCH_DIR)
		assert(dir != null)
		assert(dir.remove(path.get_file()) == OK)
	assert(not FileAccess.file_exists(path))


func _run_project_settings_cases() -> void:
	var test_key := "agent_harness/test_setting"

	# 1. Validation.
	var missing = (
		property_tools.set_project_settings_from_request({})
	)
	assert(not missing["success"])
	assert(missing["error"].contains("requires settings"))

	var empty = (
		property_tools.set_project_settings_from_request(
			{"settings": {}}
		)
	)
	assert(not empty["success"])
	assert(empty["error"].contains("at least one"))

	var too_many = (
		property_tools.set_project_settings_from_request(
			{
				"settings": {
					"a": 1, "b": 2, "c": 3, "d": 4, "e": 5,
					"f": 6, "g": 7, "h": 8, "i": 9, "j": 10,
					"k": 11
				}
			}
		)
	)
	assert(not too_many["success"])
	assert(too_many["error"].contains("at most"))

	var sensitive = (
		property_tools.set_project_settings_from_request(
			{"settings": {"agent_harness/api_key_setting": "x"}}
		)
	)
	assert(not sensitive["success"])
	assert(sensitive["error"].contains("sensitive"))

	# 2. Successful set with previous value reporting and
	# read-back verification (the key did not exist before).
	var set_result: Dictionary = (
		property_tools.set_project_settings_from_request(
			{"settings": {test_key: 42}}
		)
	)
	assert(set_result["success"])
	assert(set_result["action"] == "set_project_settings")
	assert(set_result["changed"] == true)
	assert(set_result["verified_settings"] == true)
	assert(set_result["undoable"] == false)
	assert(set_result["settings"][0]["had_previous"] == false)
	assert(set_result["settings"][0]["verified"] == true)
	assert(
		ProjectSettings.get_setting(test_key) == 42
	)

	# 3. Second set reports the previous value.
	var second: Dictionary = (
		property_tools.set_project_settings_from_request(
			{"settings": {test_key: 100}}
		)
	)
	assert(second["success"])
	assert(second["settings"][0]["had_previous"] == true)
	assert(second["settings"][0]["previous_value"] != null)

	# Cleanup: remove the harness key from the live
	# ProjectSettings of this process.
	ProjectSettings.clear(test_key)


func _run_resource_cases() -> void:
	# 1. Validation: type checks.
	var missing_type = (
		property_tools.create_resource_from_request(
			{
				"resource_path": SCRATCH_RESOURCE,
				"properties": {}
			}
		)
	)
	assert(not missing_type["success"])
	assert(missing_type["error"].contains("requires resource_type"))

	var unknown_type = (
		property_tools.create_resource_from_request(
			{
				"resource_path": SCRATCH_RESOURCE,
				"resource_type": "NotAClass",
				"properties_json": "{}"
			}
		)
	)
	assert(not unknown_type["success"])
	assert(unknown_type["error"].contains("unknown class"))

	# Node types are rejected: resources only.
	var node_type = (
		property_tools.create_resource_from_request(
			{
				"resource_path": SCRATCH_RESOURCE,
				"resource_type": "Node2D",
				"properties_json": "{}"
			}
		)
	)
	assert(not node_type["success"])
	assert(node_type["error"].contains("not a Resource"))

	# Path discipline: .tres required.
	var bad_extension = (
		property_tools.create_resource_from_request(
			{
				"resource_path": "res://x.json",
				"resource_type": "Curve",
				"properties_json": "{}"
			}
		)
	)
	assert(not bad_extension["success"])
	assert(bad_extension["error"].contains("ending in .tres"))

	# Unknown property rejected (Object.set would silently
	# ignore it otherwise).
	var unknown_property = (
		property_tools.create_resource_from_request(
			{
				"resource_path": SCRATCH_RESOURCE,
				"resource_type": "Curve",
				"properties": {"not_a_real_property": 1}
			}
		)
	)
	assert(not unknown_property["success"])
	assert(unknown_property["error"].contains("Property not found"))

	# 2. Successful creation with load-back verification.
	var created = (
		property_tools.create_resource_from_request(
			{
				"resource_path": SCRATCH_RESOURCE,
				"resource_type": "Curve",
				"properties": {"min_value": 0.0, "max_value": 5.0}
			}
		)
	)
	assert(created["success"])
	assert(created["action"] == "create_resource")
	assert(created["changed"] == true)
	assert(created["verified_write"] == true)
	assert(created["undoable"] == false)
	assert(FileAccess.file_exists(SCRATCH_RESOURCE))

	var loaded: Variant = load(SCRATCH_RESOURCE)
	assert(loaded is Curve)

	# 3. Existing files are never overwritten.
	var exists = (
		property_tools.create_resource_from_request(
			{
				"resource_path": SCRATCH_RESOURCE,
				"resource_type": "Curve",
				"properties": {}
			}
		)
	)
	assert(not exists["success"])
	assert(exists["error"].contains("already exists"))

	# 4. JSON-serializable results.
	assert(not JSON.stringify(created).is_empty())


func _run_unavailable_cases() -> void:
	# Editor-dependent tools report the explicit unavailable
	# error in a headless SceneTree process.
	var run_unavailable = (
		runtime_tools.run_scene_from_request({})
	)
	assert(not run_unavailable["success"])
	assert(run_unavailable["error"].contains("running Godot editor"))

	var stop_unavailable = (
		runtime_tools.stop_run_from_request({})
	)
	assert(not stop_unavailable["success"])
	assert(stop_unavailable["error"].contains("running Godot editor"))

	var output_unavailable = (
		runtime_tools.get_runtime_output_from_request({})
	)
	assert(not output_unavailable["success"])
	assert(output_unavailable["error"].contains("running Godot editor"))

	# run_scene validation still runs before the editor check
	# ordering is: editor first, then path. Ghost paths are
	# checked after the editor gate, so headless they are
	# reported as unavailable - the path rules are covered by
	# the live validation instead.


func _init() -> void:

	var scene_helpers = FakeSceneHelpers.new(null)

	runtime_tools = AIAgentRuntimeToolsScript.new(
		null,
		null
	)

	var variant_serializer = (
		AIAgentVariantSerializerScript.new()
	)

	property_tools = AIAgentPropertyToolsScript.new(
		scene_helpers,
		variant_serializer,
		null
	)

	_remove_file(SCRATCH_RESOURCE)

	_run_project_settings_cases()
	_run_resource_cases()
	_run_unavailable_cases()

	_remove_file(SCRATCH_RESOURCE)

	print("runtime/project/resource cases passed")

	quit()

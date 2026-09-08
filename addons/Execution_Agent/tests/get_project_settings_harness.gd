extends SceneTree

# Stand-in scene helpers are not needed here: this harness
# exercises AIAgentNodeTools.get_project_settings_from_request,
# which reads the real, live Godot ProjectSettings.
const AIAgentNodeToolsScript = preload(
	"res://addons/Execution_Agent/scene/ai_agent_node_tools.gd"
)


func _init() -> void:

	var node_tools = AIAgentNodeToolsScript.new(
		null,
		null
	)

	# 1. Exact known settings return canonical keys and
	# correct serialized values.
	var exact_result = (
		node_tools.get_project_settings_from_request(
			{
				"setting_names": [
					"application/config/name",
					"display/window/stretch/mode",
					"physics/3d/physics_engine"
				]
			}
		)
	)
	assert(exact_result["success"])
	assert(exact_result["action"] == "get_project_settings")
	assert(exact_result["settings"]["application/config/name"] == "Agent_Host")
	assert(exact_result["settings"]["display/window/stretch/mode"] == "canvas_items")
	assert(exact_result["settings"]["physics/3d/physics_engine"] == "Jolt Physics")
	assert(exact_result["missing"] == [])

	# 2. A nonexistent requested key is reported in `missing`
	# (a deterministic success, not a failure)..
	var missing_result = (
		node_tools.get_project_settings_from_request(
			{"setting_names": ["definitely/not/a/setting"]}
		)
	)
	assert(missing_result["success"])
	assert(missing_result["settings"] == {})
	assert(missing_result["missing"] == ["definitely/not/a/setting"])

	# 3. A prefix returns only matching keys, sorted
	# lexicographically, with correct bounding metadata.
	var prefix_result = (
		node_tools.get_project_settings_from_request(
			{"prefix": "display/window/"}
		)
	)
	assert(prefix_result["success"])
	assert(not prefix_result["settings"].is_empty())
	assert(prefix_result.has("total_matches"))
	assert(prefix_result.has("returned_matches"))
	assert(prefix_result.has("truncated"))
	assert(prefix_result["returned_matches"] == prefix_result["settings"].size())

	var prefix_keys: Array = []
	for key in prefix_result["settings"]:
		assert(key.begins_with("display/window/"))
		prefix_keys.append(key)

	var sorted_keys: Array = (
		prefix_keys.duplicate()
	)
	sorted_keys.sort()
	assert(prefix_keys == sorted_keys)

	# 4. Prefix limit: a limit of 1 on a prefix with
	# many keys is enforced and truncation is reported accurately.
	var limited_result = (
		node_tools.get_project_settings_from_request(
			{"prefix": "display/", "limit": 1}
		)
	)
	assert(limited_result["success"])
	assert(limited_result["returned_matches"] <= 1)
	assert(limited_result["returned_matches"] == limited_result["settings"].size())
	assert(limited_result["truncated"] == (limited_result["total_matches"] > 1))

	# 5. An invalid limit returns the structured limit error.
	var bad_limit = (
		node_tools.get_project_settings_from_request(
			{"prefix": "display/", "limit": 5000}
		)
	)
	assert(not bad_limit["success"])
	assert(bad_limit["error"].contains("limit must be an integer"))

	# 6. An unfiltered "dump everything" request is rejected.
	var unfiltered = (
		node_tools.get_project_settings_from_request({})
	)
	assert(not unfiltered["success"])
	assert(
		unfiltered["error"]
		== "get_project_settings requires at least one of non-empty setting_names or prefix."
	)

	# 7. Sensitive-setting protection: a setting whose name
	# contains a sensitive token is excluded (name only), never
	# exposed. The synthetic key is in-memory only and cleared
	# immediately；it is not a real credential and never persists.
	var synthetic_key := "ai_agent_test/token_value"
	ProjectSettings.set_setting(synthetic_key, "should_never_be_exposed")

	var sensitive_exact = (
		node_tools.get_project_settings_from_request(
			{"setting_names": [synthetic_key]}
		)
	)
	assert(sensitive_exact["success"])
	assert(not sensitive_exact["settings"].has(synthetic_key))
	assert(sensitive_exact["redacted"].has(synthetic_key))

	var sensitive_prefix = (
		node_tools.get_project_settings_from_request(
			{"prefix": synthetic_key}
		)
	)
	assert(not sensitive_prefix["settings"].has(synthetic_key))
	assert(sensitive_prefix["redacted"].has(synthetic_key))

	ProjectSettings.clear(synthetic_key)
	assert(not ProjectSettings.has_setting(synthetic_key))

	# 8. Multi-type serialization: window-size settings area
	# integers via the shared Variant serializer. (Real Godot 4.x
	# always exposes these defaults.)
	var int_result = (
		node_tools.get_project_settings_from_request(
			{"prefix": "display/window/size/", "limit": 10}
		)
	)
	assert(int_result["success"])
	assert(not int_result["settings"].is_empty())
	for key in int_result["settings"]:
		if key.contains("viewport"):
			assert(typeof(int_result["settings"][key]) == TYPE_INT)

	# 9. Determinism: repeated identical calls are byte-equivalent.
	var repeat_result = (
		node_tools.get_project_settings_from_request(
			{"prefix": "display/window/"}
		)
	)
	assert(repeat_result == prefix_result)

	# 10. The result is JSON-serializable.
	var serialized := JSON.stringify(prefix_result)
	assert(not serialized.is_empty())
	assert(serialized.contains("display/window"))

	print("get_project_settings harness passed")
	quit()

@tool
extends RefCounted

class_name AIAgentRouter


var node_tools: AIAgentNodeTools
var property_tools: AIAgentPropertyTools
var editor_tools: RefCounted
var script_tools: AIAgentScriptTools
var scene_file_tools: AIAgentSceneFileTools
var runtime_tools: AIAgentRuntimeTools
var refactor_tools: RefCounted


func _init(
	p_node_tools: AIAgentNodeTools,
	p_property_tools: AIAgentPropertyTools,
	p_editor_tools: RefCounted,
	p_script_tools: AIAgentScriptTools,
	p_scene_file_tools: AIAgentSceneFileTools,
	p_runtime_tools: AIAgentRuntimeTools,
	p_refactor_tools: RefCounted
) -> void:

	node_tools = p_node_tools

	property_tools = p_property_tools

	editor_tools = p_editor_tools

	script_tools = p_script_tools

	scene_file_tools = p_scene_file_tools

	runtime_tools = p_runtime_tools

	refactor_tools = p_refactor_tools


# ==========================================
# Request routing
# ==========================================


func route_request(
	method: String,
	path: String,
	body_text: String
) -> Dictionary:

	# ======================================
	# Route: /ping
	# ======================================

	if (
		method == "POST"
		and path == "/ping"
	):

		return {
			"success": true,
			"message": (
				"AI Agent editor bridge is running."
			)
		}

	# ======================================
	# Route: /scene_tree
	# ======================================

	if (
		method == "GET"
		and path == "/scene_tree"
	):

		return node_tools.get_scene_tree()

	# ======================================
	# Route: /scene_tree (depth-bounded POST
	# variant used by the agent)
	# ======================================

	if (
		method == "POST"
		and path == "/scene_tree"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"get_scene_tree_from_request"
		)


	# ======================================
	# Route: /find_nodes
	# ======================================

	if (
		method == "POST"
		and path == "/find_nodes"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"find_nodes_from_request"
		)

	# ======================================
	# Route: /get_project_settings
	# ======================================

	if (
		method == "POST"
		and path == "/get_project_settings"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"get_project_settings_from_request"
		)

	# ======================================
	# Routes: project/editor inspection
	# ======================================

	if method == "GET" and path == "/list_autoloads":
		return editor_tools.list_autoloads()

	if method == "GET" and path == "/get_editor_state":
		return editor_tools.get_editor_state()

	if method == "GET" and path == "/list_scenes_in_project":
		return editor_tools.list_scenes_in_project()

	if method == "GET" and path == "/get_undo_history_summary":
		return editor_tools.get_undo_history_summary()

	# ======================================
	# Route: /find_nodes_by_script
	# ======================================

	if (
		method == "POST"
		and path == "/find_nodes_by_script"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"find_nodes_by_script_from_request"
		)

	# ======================================
	# Route: /find_nodes_by_group
	# ======================================

	if (
		method == "POST"
		and path == "/find_nodes_by_group"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"find_nodes_by_group_from_request"
		)

	# ======================================
	# Route: /count_nodes
	# ======================================

	if (
		method == "POST"
		and path == "/count_nodes"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"count_nodes_from_request"
		)

	# ======================================
	# Route: /validate_node_type
	# ======================================

	if (
		method == "POST"
		and path == "/validate_node_type"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"validate_node_type_from_request"
		)

	# ======================================
	# Route: /list_available_node_types
	# ======================================

	if (
		method == "POST"
		and path == "/list_available_node_types"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"list_available_node_types_from_request"
		)

	# ======================================
	# Route: /get_node_class_info
	# ======================================

	if (
		method == "POST"
		and path == "/get_node_class_info"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"get_node_class_info_from_request"
		)

	# ======================================
	# Route: /list_node_signals
	# ======================================

	if (
		method == "POST"
		and path == "/list_node_signals"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"list_node_signals_from_request"
		)

	# ======================================
	# Route: /list_node_groups
	# ======================================

	if (
		method == "POST"
		and path == "/list_node_groups"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"list_node_groups_from_request"
		)

	# ======================================
	# Route: /get_node_properties
	# ======================================

	if (
		method == "POST"
		and path == "/get_node_properties"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"get_node_properties_from_request"
		)

	# ======================================
	# Route: /get_node_property
	# ======================================

	if (
		method == "POST"
		and path == "/get_node_property"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"get_node_property_from_request"
		)

	# ======================================
	# Route: /set_properties
	# ======================================

	if (
		method == "POST"
		and path == "/set_properties"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"set_properties_from_request"
		)

	# ======================================
	# Route: /create_node
	# ======================================

	if (
		method == "POST"
		and path == "/create_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"create_node_from_request"
		)

	# ======================================
	# Route: /rename_node
	# ======================================

	if (
		method == "POST"
		and path == "/rename_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"rename_node_from_request"
		)

	# ======================================
	# Route: /delete_node
	# ======================================

	if (
		method == "POST"
		and path == "/delete_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"delete_node_from_request"
		)

	# ======================================
	# Route: /reparent_node
	# ======================================

	if (
		method == "POST"
		and path == "/reparent_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"reparent_node_from_request"
		)

	# ======================================
	# Route: /duplicate_node
	# ======================================

	if (
		method == "POST"
		and path == "/duplicate_node"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"duplicate_node_from_request"
		)

	# ======================================
	# Route: /move_child
	# ======================================

	if (
		method == "POST"
		and path == "/move_child"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"move_child_from_request"
		)

	# ======================================
	# Route: /add_to_group
	# ======================================

	if (
		method == "POST"
		and path == "/add_to_group"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"add_to_group_from_request"
		)

	# ======================================
	# Route: /remove_from_group
	# ======================================

	if (
		method == "POST"
		and path == "/remove_from_group"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"remove_from_group_from_request"
		)

	# ======================================
	# Route: /list_node_connections
	# ======================================

	if (
		method == "POST"
		and path == "/list_node_connections"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"list_node_connections_from_request"
		)

	# ======================================
	# Route: /connect_signal
	# ======================================

	if (
		method == "POST"
		and path == "/connect_signal"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"connect_signal_from_request"
		)

	# ======================================
	# Route: /disconnect_signal
	# ======================================

	if (
		method == "POST"
		and path == "/disconnect_signal"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"disconnect_signal_from_request"
		)

	# ======================================
	# Routes: script tools
	# ======================================

	if (
		method == "POST"
		and path == "/create_script"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"create_script_from_request"
		)

	if (
		method == "POST"
		and path == "/attach_script"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"attach_script_from_request"
		)

	if (
		method == "POST"
		and path == "/detach_script"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"detach_script_from_request"
		)

	if (
		method == "POST"
		and path == "/get_script_content"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"get_script_content_from_request"
		)

	if (
		method == "POST"
		and path == "/list_script_diagnostics"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"list_script_diagnostics_from_request"
		)

	if (
		method == "POST"
		and path == "/edit_script"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"edit_script_from_request"
		)

	if (
		method == "POST"
		and path == "/replace_in_script"
	):

		return _handle_json_route(
			body_text,
			script_tools,
			"replace_in_script_from_request"
		)

	# ======================================
	# Routes: scene file tools
	# ======================================

	if (
		method == "POST"
		and path == "/save_scene"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"save_scene_from_request"
		)

	if (
		method == "POST"
		and path == "/create_scene"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"create_scene_from_request"
		)

	if (
		method == "POST"
		and path == "/instantiate_scene"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"instantiate_scene_from_request"
		)

	if (
		method == "POST"
		and path == "/get_scene_dependencies"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"get_scene_dependencies_from_request"
		)

	if (
		method == "POST"
		and path == "/get_scene_tree_of"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"get_scene_tree_of_from_request"
		)

	if (
		method == "POST"
		and path == "/list_open_scenes"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"list_open_scenes_from_request"
		)

	# ======================================
	# Routes: property introspection and resources
	# ======================================

	if (
		method == "POST"
		and path == "/get_property_info"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"get_property_info_from_request"
		)

	if (
		method == "POST"
		and path == "/assign_resource_to_property"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"assign_resource_to_property_from_request"
		)

	if (
		method == "POST"
		and path == "/get_resource_info"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"get_resource_info_from_request"
		)

	if (
		method == "POST"
		and path == "/get_node_children_summary"
	):

		return _handle_json_route(
			body_text,
			node_tools,
			"get_node_children_summary_from_request"
		)

	# ======================================
	# Routes: project inspection
	# ======================================

	if (
		method == "POST"
		and path == "/list_project_files"
	):

		return _handle_json_route(
			body_text,
			editor_tools,
			"list_project_files_from_request"
		)

	if (
		method == "POST"
		and path == "/search_in_files"
	):

		return _handle_json_route(
			body_text,
			editor_tools,
			"search_in_files_from_request"
		)

	if (
		method == "POST"
		and path == "/get_global_class_list"
	):

		return _handle_json_route(
			body_text,
			editor_tools,
			"get_global_class_list_from_request"
		)

	if (
		method == "POST"
		and path == "/get_input_map"
	):

		return _handle_json_route(
			body_text,
			editor_tools,
			"get_input_map_from_request"
		)

	# ======================================
	# Routes: scene navigation
	# ======================================

	if (
		method == "POST"
		and path == "/open_scene"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"open_scene_from_request"
		)

	if (
		method == "POST"
		and path == "/save_scene_as"
	):

		return _handle_json_route(
			body_text,
			scene_file_tools,
			"save_scene_as_from_request"
		)

	# ======================================
	# Routes: runtime (playtest loop)
	# ======================================

	if (
		method == "POST"
		and path == "/run_scene"
	):

		return _handle_json_route(
			body_text,
			runtime_tools,
			"run_scene_from_request"
		)

	if (
		method == "POST"
		and path == "/stop_run"
	):

		return _handle_json_route(
			body_text,
			runtime_tools,
			"stop_run_from_request"
		)

	if (
		method == "POST"
		and path == "/get_runtime_output"
	):

		return _handle_json_route(
			body_text,
			runtime_tools,
			"get_runtime_output_from_request"
		)

	# ======================================
	# Routes: project settings and resources
	# ======================================

	if (
		method == "POST"
		and path == "/set_project_settings"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"set_project_settings_from_request"
		)

	if (
		method == "POST"
		and path == "/create_resource"
	):

		return _handle_json_route(
			body_text,
			property_tools,
			"create_resource_from_request"
		)

	# ======================================
	# Routes: project linting and refactoring
	# ======================================

	if (
		method == "POST"
		and path == "/scan_project_issues"
	):

		return _handle_json_route(
			body_text,
			editor_tools,
			"scan_project_issues_from_request"
		)

	if (
		method == "POST"
		and path == "/rename_script"
	):

		return _handle_json_route(
			body_text,
			refactor_tools,
			"rename_script_from_request"
		)

	if (
		method == "POST"
		and path == "/find_replace_across_files"
	):

		return _handle_json_route(
			body_text,
			refactor_tools,
			"find_replace_across_files_from_request"
		)

	# ======================================
	# Unknown route
	# ======================================

	return {
		"success": false,
		"error": (
			"Unknown endpoint: "
			+ method
			+ " "
			+ path
		)
	}


# ==========================================
# JSON route helper
# ==========================================


func _handle_json_route(
	body_text: String,
	target,
	method_name: String
) -> Dictionary:

	var parse_result := (
		parse_request_json(
			body_text
		)
	)

	if not parse_result["success"]:
		return parse_result

	return target.call(
		method_name,
		parse_result["data"]
	)


# ==========================================
# JSON parsing
# ==========================================


func parse_request_json(
	body_text: String
) -> Dictionary:

	var json := JSON.new()

	var parse_error := (
		json.parse(
			body_text
		)
	)

	if parse_error != OK:

		return {
			"success": false,
			"error": (
				"Invalid JSON request body."
			)
		}

	var data = (
		json.data
	)

	if not data is Dictionary:

		return {
			"success": false,
			"error": (
				"Request JSON must be an object."
			)
		}

	return {
		"success": true,
		"data": data
	}

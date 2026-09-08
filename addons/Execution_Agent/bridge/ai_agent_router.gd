@tool
extends RefCounted

class_name AIAgentRouter


var node_tools: AIAgentNodeTools
var property_tools: AIAgentPropertyTools
var editor_tools: RefCounted


func _init(
	p_node_tools: AIAgentNodeTools,
	p_property_tools: AIAgentPropertyTools,
	p_editor_tools: RefCounted
) -> void:

	node_tools = p_node_tools

	property_tools = p_property_tools

	editor_tools = p_editor_tools


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

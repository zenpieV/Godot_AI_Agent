extends Node


var server := TCPServer.new()


func _ready():
	var error = server.listen(8080)

	if error != OK:
		push_error(
            "Failed to start Godot bridge on port 8080."
		)
		return

	print(
        "Godot bridge running on port 8080"
	)


func _process(_delta):
	if server.is_connection_available():
		var client = server.take_connection()

		_handle_client(client)


# =========================================================
# HTTP request handling
# =========================================================


func _handle_client(client: StreamPeerTCP):
	var request = _read_http_request(client)

	if request.is_empty():
		_send_json(
			client,
			400,
			{
				"success": false,
				"error": "Empty HTTP request."
			}
		)

		return


	var request_line = request.get_slice(
		"\r\n",
		0
	)


	if request_line.begins_with(
        "GET /scene_tree "
	):

		_handle_scene_tree(client)

		return


	if request_line.begins_with(
        "POST /create_node "
	):

		_handle_create_node(
			client,
			request
		)

		return


	_send_json(
		client,
		404,
		{
			"success": false,
			"error": "Unknown endpoint."
		}
	)


# =========================================================
# Read HTTP request
# =========================================================


func _read_http_request(
	client: StreamPeerTCP
) -> String:

	var request := ""

	var timeout_at = (
		Time.get_ticks_msec()
		+ 1000
	)


	while (
		Time.get_ticks_msec()
		< timeout_at
	):

		client.poll()

		var available = (
			client.get_available_bytes()
		)


		if available > 0:

			request += (
				client.get_utf8_string(
					available
				)
			)


		if request.contains(
            "\r\n\r\n"
		):

			var content_length = (
				_get_content_length(
					request
				)
			)

			var parts = request.split(
				"\r\n\r\n",
				true,
				1
			)

			var body := ""

			if parts.size() > 1:
				body = parts[1]


			if (
				body.to_utf8_buffer().size()
				>= content_length
			):
				return request


		OS.delay_msec(1)


	return request


func _get_content_length(
	request: String
) -> int:

	var lines = request.split(
        "\r\n"
	)


	for line in lines:

		var lower_line = (
			line.to_lower()
		)


		if lower_line.begins_with(
            "content-length:"
		):

			return int(
				line.get_slice(
					":",
					1
				).strip_edges()
			)


	return 0


# =========================================================
# GET /scene_tree
# =========================================================


func _handle_scene_tree(
	client: StreamPeerTCP
):

	var current_scene = (
		get_tree().current_scene
	)


	if current_scene == null:

		_send_json(
			client,
			500,
			{
				"success": false,
				"error": (
                    "No current scene exists."
				)
			}
		)

		return


	var scene_tree = (
		_build_scene_tree(
			current_scene
		)
	)


	_send_json(
		client,
		200,
		scene_tree
	)


# =========================================================
# POST /create_node
# =========================================================


func _handle_create_node(
	client: StreamPeerTCP,
	request: String
):

	var parts = request.split(
		"\r\n\r\n",
		true,
		1
	)


	if parts.size() < 2:

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
                    "Request body is missing."
				)
			}
		)

		return


	var body = parts[1]

	var data = JSON.parse_string(
		body
	)


	if typeof(data) != TYPE_DICTIONARY:

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
                    "Request body must be "
					+ "valid JSON."
				)
			}
		)

		return


	var parent_path = str(
		data.get(
			"parent_path",
            ""
		)
	)

	var node_type = str(
		data.get(
			"node_type",
            ""
		)
	)

	var node_name = str(
		data.get(
			"node_name",
            ""
		)
	)


	if (
		parent_path.is_empty()
		or node_type.is_empty()
		or node_name.is_empty()
	):

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
                    "parent_path, node_type "
					+ "and node_name are required."
				)
			}
		)

		return


	var current_scene = (
		get_tree().current_scene
	)


	if current_scene == null:

		_send_json(
			client,
			500,
			{
				"success": false,
				"error": (
                    "No current scene exists."
				)
			}
		)

		return


	var parent: Node


	if parent_path == ".":
		parent = current_scene

	else:
		parent = (
			current_scene.get_node_or_null(
				NodePath(parent_path)
			)
		)


	if parent == null:

		_send_json(
			client,
			404,
			{
				"success": false,
				"error": (
                    "Parent node not found: "
					+ parent_path
				)
			}
		)

		return


	if (
		not ClassDB.class_exists(
			node_type
		)
	):

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
                    "Unknown Godot class: "
					+ node_type
				)
			}
		)

		return


	if (
		not ClassDB.can_instantiate(
			node_type
		)
	):

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
                    "Godot class cannot "
					+ "be instantiated: "
					+ node_type
				)
			}
		)

		return


	var created_object = (
		ClassDB.instantiate(
			node_type
		)
	)


	if not created_object is Node:

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
					node_type
					+ " is not a Node type."
				)
			}
		)

		return


	var new_node = (
		created_object as Node
	)


	var safe_name = (
		node_name.validate_node_name()
	)


	if safe_name != node_name:

		new_node.free()

		_send_json(
			client,
			400,
			{
				"success": false,
				"error": (
                    "Invalid node name: "
					+ node_name
				)
			}
		)

		return


	for existing_child in (
		parent.get_children()
	):

		if (
			existing_child.name
			== node_name
		):

			new_node.free()

			_send_json(
				client,
				409,
				{
					"success": false,
					"error": (
                        "A child named '"
						+ node_name
						+ "' already exists."
					)
				}
			)

			return


	new_node.name = node_name

	parent.add_child(
		new_node
	)


	var created_path = str(
		current_scene.get_path_to(
			new_node
		)
	)


	_send_json(
		client,
		200,
		{
			"success": true,
			"action": "create_node",
			"node_name": new_node.name,
			"node_type": new_node.get_class(),
			"parent_path": parent_path,
			"created_path": created_path,
			"persistent": false,
			"message": (
                "Runtime node created successfully."
			)
		}
	)


# =========================================================
# Scene tree serialization
# =========================================================


func _build_scene_tree(
	node: Node
):

	var children_data = []


	for child in (
		node.get_children()
	):

		children_data.append(
			_build_scene_tree(
				child
			)
		)


	return {
		"name": node.name,
		"type": node.get_class(),
		"children": children_data
	}


# =========================================================
# HTTP response helper
# =========================================================


func _send_json(
	client: StreamPeerTCP,
	status_code: int,
	payload: Dictionary
):

	var body = JSON.stringify(
		payload
	)


	var status_text := "OK"


	if status_code == 400:
		status_text = "Bad Request"

	elif status_code == 404:
		status_text = "Not Found"

	elif status_code == 409:
		status_text = "Conflict"

	elif status_code >= 500:
		status_text = (
            "Internal Server Error"
		)


	var content_length = (
		body.to_utf8_buffer().size()
	)


	var response = (
        "HTTP/1.1 "
		+ str(status_code)
		+ " "
		+ status_text
		+ "\r\n"
		+ "Content-Type: application/json\r\n"
		+ "Content-Length: "
		+ str(content_length)
		+ "\r\n"
		+ "Connection: close\r\n"
		+ "\r\n"
		+ body
	)


	client.put_data(
		response.to_utf8_buffer()
	)

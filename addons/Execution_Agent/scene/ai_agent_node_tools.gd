@tool
extends RefCounted

class_name AIAgentNodeTools


# Bounded-output cap for find_nodes / find_nodes_by_script
# / find_nodes_by_group: beyond this the response reports
# total_matches + truncated instead of dumping nodes.

const FIND_NODES_MAX_RESULTS := 200


var scene_helpers: AIAgentSceneHelpers
var undo_redo: EditorUndoRedoManager

const DEFAULT_NODE_TYPE_RESULT_LIMIT := 50
const MAX_NODE_TYPE_RESULT_LIMIT := 100

# Project-settings inspection bounds, mirroring the
# node-type-discovery convention above.
const DEFAULT_SETTINGS_RESULT_LIMIT := 50
const MAX_SETTINGS_RESULT_LIMIT := 100

const VariantSerializerScript = preload(
	"res://addons/Execution_Agent/serialization/ai_agent_variant_serializer.gd"
)

# Tokens that mark a project-setting name as sensitive.
# Settings whose name contains one of these are excluded
# from the response (names only, never values).
const SENSITIVE_SETTING_TOKENS := [
	"password",
	"token",
	"secret",
	"api_key",
	"credential",
	"private_key"
]


func _init(
	p_scene_helpers: AIAgentSceneHelpers,
	p_undo_redo: EditorUndoRedoManager
) -> void:

	scene_helpers = p_scene_helpers

	undo_redo = p_undo_redo


# ==========================================
# get_scene_tree
# ==========================================


func get_scene_tree() -> Dictionary:

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	return {
		"success": true,
		"action": "get_scene_tree",
		"scene_tree": (
			serialize_scene_node(
				edited_scene_root,
				edited_scene_root
			)
		)
	}


func get_scene_tree_from_request(
	data: Dictionary
) -> Dictionary:

	# Depth-bounded variant of get_scene_tree: with
	# max_depth set, nodes deeper than the bound are
	# cut and reported with children_truncated so a
	# huge scene never floods the conversation. The
	# caller drills into truncated nodes with
	# get_node_children_summary.

	var max_depth := 0

	if data.has("max_depth") and data["max_depth"] != null:

		if (
			typeof(data["max_depth"]) != TYPE_INT
			and typeof(data["max_depth"]) != TYPE_FLOAT
		):

			return {
				"success": false,
				"error": (
					"get_scene_tree max_depth must "
					+ "be an integer between 1 and "
					+ "50."
				)
			}

		max_depth = int(data["max_depth"])

		if max_depth < 1 or max_depth > 50:

			return {
				"success": false,
				"error": (
					"get_scene_tree max_depth must "
					+ "be an integer between 1 and "
					+ "50."
				)
			}

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	var tree := serialize_scene_node(
		edited_scene_root,
		edited_scene_root,
		max_depth
	)

	return {
		"success": true,
		"action": "get_scene_tree",
		"max_depth": max_depth,
		"truncated": tree_has_depth_truncation(tree),
		"scene_tree": tree
	}


func serialize_scene_node(
	edited_scene_root: Node,
	current_node: Node,
	max_depth: int = 0,
	current_depth: int = 0
) -> Dictionary:

	# With max_depth > 0 the serialization stops at
	# that depth: deeper nodes are never visited and
	# the cut is reported per-node with
	# children_truncated (0 = unlimited, the
	# historical behavior).

	var children_truncated := false

	if (
		max_depth > 0
		and current_depth >= max_depth
	):

		children_truncated = (
			current_node.get_child_count() > 0
		)

		return {
			"name": (
				str(current_node.name)
			),
			"node_type": (
				current_node.get_class()
			),
			"path": (
				scene_helpers
				.get_relative_node_path(
					edited_scene_root,
					current_node
				)
			),
			"is_root": (
				current_node
				== edited_scene_root
			),
			"children": [],
			"children_truncated": children_truncated
		}

	var children: Array = []

	for child in current_node.get_children():

		if child is Node:

			children.append(
				serialize_scene_node(
					edited_scene_root,
					child,
					max_depth,
					current_depth + 1
				)
			)

	return {
		"name": (
			str(current_node.name)
		),
		"node_type": (
			current_node.get_class()
		),
		"path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				current_node
			)
		),
		"is_root": (
			current_node
			== edited_scene_root
		),
		"children": children
	}


func tree_has_depth_truncation(
	tree: Dictionary
) -> bool:

	if tree.get("children_truncated", false):
		return true

	for child in tree.get("children", []):

		if child is Dictionary:

			if tree_has_depth_truncation(child):
				return true

	return false


# ==========================================
# find_nodes
# ==========================================


func find_nodes_from_request(
	data: Dictionary
) -> Dictionary:

	var filters := _parse_find_node_filters(data)

	if not filters["valid"]:
		return {
			"success": false,
			"error": filters["error"]
		}

	var node_name_filter: String = (
		filters["node_name_filter"]
	)

	var node_type_filter: String = (
		filters["node_type_filter"]
	)

	var parent_path_filter: String = (
		filters["parent_path_filter"]
	)

	var name_match: String = (
		filters["name_match"]
	)

	var include_root: bool = (
		filters["include_root"]
	)

	var include_subclasses: bool = (
		filters["include_subclasses"]
	)

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	var search_root: Node = (
		edited_scene_root
	)

	if not parent_path_filter.is_empty():

		var parent_result: Dictionary = (
			scene_helpers
			.resolve_node_or_error(
				parent_path_filter
			)
		)

		if not parent_result["success"]:

			return {
				"success": false,
				"error": (
					"Parent node not found: "
					+ parent_path_filter
					+ ". "
					+ str(
						parent_result.get(
							"error",
							"Unknown path error."
						)
					)
				)
			}

		search_root = (
			parent_result["node"]
		)

		parent_path_filter = (
			parent_result["normalized_path"]
		)

	var matching_nodes: Array = []

	collect_matching_nodes(
		edited_scene_root,
		search_root,
		matching_nodes,
		node_name_filter,
		node_type_filter,
		name_match,
		include_root,
		"",
		"",
		include_subclasses
	)

	# Bounded output: never dump an unbounded node list
	# into the conversation. total_matches preserves the
	# true count; truncated says so.

	var total_matches := matching_nodes.size()

	var truncated := total_matches > FIND_NODES_MAX_RESULTS

	return {
		"success": true,
		"action": "find_nodes",
		"count": matching_nodes.slice(
			0,
			FIND_NODES_MAX_RESULTS
		).size(),
		"total_matches": total_matches,
		"truncated": truncated,
		"limit": FIND_NODES_MAX_RESULTS,
		"node_name_filter": node_name_filter,
		"node_type_filter": node_type_filter,
		"parent_path_filter": parent_path_filter,
		"name_match": name_match,
		"include_root": include_root,
		"include_subclasses": include_subclasses,
		"nodes": matching_nodes.slice(
			0,
			FIND_NODES_MAX_RESULTS
		)
	}


# Shared parser for the find_nodes / count_nodes
# filter shape. Returns valid=true with the parsed
# filters, or valid=false with the established
# error message. Both tools must see identical
# filter semantics.
func _parse_find_node_filters(
	data: Dictionary
) -> Dictionary:

	var node_name_filter := ""
	var node_type_filter := ""
	var parent_path_filter := ""
	var name_match := "exact"
	var include_root := false

	if (
		data.has("node_name")
		and data["node_name"] != null
	):

		node_name_filter = (
			str(data["node_name"])
		)

	if (
		data.has("node_type")
		and data["node_type"] != null
	):

		node_type_filter = (
			str(data["node_type"])
		)

	if (
		data.has("parent_path")
		and data["parent_path"] != null
	):

		parent_path_filter = (
			str(data["parent_path"])
		)

	if (
		data.has("name_match")
		and data["name_match"] != null
	):

		name_match = (
			str(data["name_match"])
			.to_lower()
		)

	if data.has("include_root"):

		if typeof(data["include_root"]) != TYPE_BOOL:

			return {
				"valid": false,
				"error": (
					"include_root must be a boolean."
				)
			}

		include_root = data["include_root"]

	var include_subclasses := false

	if data.has("include_subclasses"):

		if typeof(data["include_subclasses"]) != TYPE_BOOL:

			return {
				"valid": false,
				"error": (
					"include_subclasses must be a "
					+ "boolean."
				)
			}

		include_subclasses = data["include_subclasses"]

	var valid_name_match_modes := [
		"exact",
		"contains",
		"starts_with",
		"ends_with"
	]

	if (
		not valid_name_match_modes.has(
			name_match
		)
	):

		return {
			"valid": false,
			"error": (
				"Invalid name_match mode: "
				+ name_match
			)
		}

	return {
		"valid": true,
		"error": "",
		"node_name_filter": node_name_filter,
		"node_type_filter": node_type_filter,
		"parent_path_filter": parent_path_filter,
		"name_match": name_match,
		"include_root": include_root,
		"include_subclasses": include_subclasses
	}


# count_nodes
# ==========================================
# Read-only aggregate inspection: counts nodes
# matching the exact same filter semantics as
# find_nodes, reusing the same traversal and
# name/type matching, but returns only the count
# and never the matching node list.


func count_nodes_from_request(
	data: Dictionary
) -> Dictionary:

	var filters := _parse_find_node_filters(data)

	if not filters["valid"]:
		return {
			"success": false,
			"error": filters["error"]
		}

	var node_name_filter: String = (
		filters["node_name_filter"]
	)

	var node_type_filter: String = (
		filters["node_type_filter"]
	)

	var parent_path_filter: String = (
		filters["parent_path_filter"]
	)

	var name_match: String = (
		filters["name_match"]
	)

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	var search_root: Node = (
		edited_scene_root
	)

	if not parent_path_filter.is_empty():

		var parent_result: Dictionary = (
			scene_helpers
			.resolve_node_or_error(
				parent_path_filter
			)
		)

		if not parent_result["success"]:

			return {
				"success": false,
				"error": (
					"Parent node not found: "
					+ parent_path_filter
					+ ". "
					+ str(
						parent_result.get(
							"error",
							"Unknown path error."
						)
					)
				)
			}

		search_root = (
			parent_result["node"]
		)

		parent_path_filter = (
			parent_result["normalized_path"]
		)

	# count_nodes intentionally keeps the find_nodes
	# default of include_root=false; the tool has no
	# include_root field of its own.
	var matching_nodes: Array = []

	collect_matching_nodes(
		edited_scene_root,
		search_root,
		matching_nodes,
		node_name_filter,
		node_type_filter,
		name_match,
		false,
		"",
		"",
		filters["include_subclasses"]
	)

	return {
		"success": true,
		"action": "count_nodes",
		"count": matching_nodes.size(),
		"node_name_filter": node_name_filter,
		"node_type_filter": node_type_filter,
		"parent_path_filter": parent_path_filter,
		"name_match": name_match
	}


func collect_matching_nodes(
	edited_scene_root: Node,
	current_node: Node,
	matching_nodes: Array,
	node_name_filter: String,
	node_type_filter: String,
	name_match: String,
	include_root: bool,
	script_path_filter: String = "",
	group_name_filter: String = "",
	include_subclasses: bool = false
) -> void:

	var is_root := (
		current_node
		== edited_scene_root
	)

	var should_consider_node := true

	if (
		is_root
		and not include_root
	):

		should_consider_node = false

	if should_consider_node:

		var name_matches := true
		var type_matches := true
		var script_matches := true
		var group_matches := true

		if not node_name_filter.is_empty():

			name_matches = (
				node_name_matches(
					str(current_node.name),
					node_name_filter,
					name_match
				)
			)

		if not node_type_filter.is_empty():

			if include_subclasses:

				type_matches = (
					ClassDB.is_parent_class(
						current_node.get_class(),
						node_type_filter
					)
					or current_node.get_class()
					== node_type_filter
				)

			else:

				type_matches = (
					current_node.get_class()
					== node_type_filter
				)

		if not script_path_filter.is_empty():

			var attached_script = (
				current_node.get_script()
			)

			if attached_script == null:

				script_matches = false

			else:

				script_matches = (
					str(
						attached_script
						.resource_path
					)
					== script_path_filter
				)

		if not group_name_filter.is_empty():

			# Node.is_in_group() is the authoritative
			# live membership API and is exact and
			# case-sensitive, matching Godot's own
			# group-name identity.
			group_matches = (
				current_node.is_in_group(
					group_name_filter
				)
			)

		if (
			name_matches
			and type_matches
			and script_matches
			and group_matches
		):

			matching_nodes.append(
				{
					"name": (
						str(current_node.name)
					),
					"node_type": (
						current_node
						.get_class()
					),
					"path": (
						scene_helpers
						.get_relative_node_path(
							edited_scene_root,
							current_node
						)
					),
					"is_root": is_root
				}
			)

	for child in current_node.get_children():

		if child is Node:

			collect_matching_nodes(
				edited_scene_root,
				child,
				matching_nodes,
				node_name_filter,
				node_type_filter,
				name_match,
				include_root,
				script_path_filter,
				group_name_filter
			)


func node_name_matches(
	node_name: String,
	filter_name: String,
	name_match: String
) -> bool:

	var normalized_name := (
		node_name.to_lower()
	)

	var normalized_filter := (
		filter_name.to_lower()
	)

	match name_match:

		"exact":
			return (
				normalized_name
				== normalized_filter
			)

		"contains":
			return (
				normalized_name.contains(
					normalized_filter
				)
			)

		"starts_with":
			return (
				normalized_name.begins_with(
					normalized_filter
				)
			)

		"ends_with":
			return (
				normalized_name.ends_with(
					normalized_filter
				)
			)

	return false


# ==========================================
# create_node
# ==========================================


func create_node_from_request(
	data: Dictionary
) -> Dictionary:

	if (
		not data.has("parent_path")
		or not data.has("node_type")
		or not data.has("node_name")
	):

		return {
			"success": false,
			"error": (
				"create_node requires parent_path, "
				+ "node_type, and node_name."
			)
		}

	var parent_path: String = (
		str(data["parent_path"])
	)

	var node_type: String = (
		str(data["node_type"])
	)

	# Strict name validation: a null or empty name would
	# create an unresolvable node path.

	if typeof(data["node_name"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"create_node node_name must be "
				+ "a string."
			)
		}

	var node_name: String = (
		data["node_name"]
	)

	if node_name.strip_edges().is_empty():

		return {
			"success": false,
			"error": (
				"create_node requires a non-empty "
				+ "node_name."
			)
		}

	var parent_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			parent_path
		)
	)

	if not parent_result["success"]:

		return {
			"success": false,
			"error": (
				"Parent node not found: "
				+ parent_path
				+ ". "
				+ str(
					parent_result.get(
						"error",
						"Unknown path error."
					)
				)
			)
		}

	var edited_scene_root: Node = (
		parent_result["scene_root"]
	)

	var parent_node: Node = (
		parent_result["node"]
	)

	parent_path = (
		parent_result["normalized_path"]
	)

	if not ClassDB.class_exists(
		node_type
	):

		return {
			"success": false,
			"error": (
				"Unknown Godot node type: "
				+ node_type
			)
		}

	var new_node := (
		ClassDB.instantiate(
			node_type
		)
	)

	if new_node == null:

		return {
			"success": false,
			"error": (
				"Failed to instantiate node type: "
				+ node_type
			)
		}

	if not new_node is Node:

		return {
			"success": false,
			"error": (
				node_type
				+ " is not a Node type."
			)
		}

	# Explicit typed reference: ClassDB.instantiate()
	# returns Object, and the runtime "is Node" check
	# above doesn't statically narrow that. The
	# post-operation verification below calls a
	# helper with a strictly Node-typed parameter, so
	# we cast once, here, right after it's verified.
	var new_child_node: Node = (
		new_node as Node
	)

	new_node.name = node_name

	undo_redo.create_action(
		"AI Agent: Create "
		+ node_name
	)

	undo_redo.add_do_method(
		parent_node,
		"add_child",
		new_node
	)

	undo_redo.add_do_method(
		new_node,
		"set_owner",
		edited_scene_root
	)

	undo_redo.add_undo_method(
		parent_node,
		"remove_child",
		new_node
	)

	undo_redo.commit_action()

	# --------------------------------------
	# Post-operation verification
	# --------------------------------------
	#
	# commit_action() executes its "do" methods
	# synchronously (the default execute=true),
	# so new_node is already a real child of
	# parent_node at this point. We read its
	# actual state back rather than assuming the
	# request succeeded exactly as asked.
	#
	# This also catches a real Godot behavior:
	# Node.add_child() silently renames the new
	# child if a sibling already has the same
	# name, instead of failing. Without this
	# check, "created_path" would previously be
	# built purely from the requested node_name
	# and could silently be wrong.

	var actual_node_name: String = (
		str(new_node.name)
	)

	var created_path: String = (
		scene_helpers
		.get_relative_node_path(
			edited_scene_root,
			new_child_node
		)
	)

	var verify_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			created_path
		)
	)

	var verified_exists: bool = (
		verify_result["success"]
	)

	return {
		"success": true,
		"action": "create_node",
		"message": (
			"Undoable node created successfully "
			+ "in the Godot editor."
		),
		"node_name": node_name,
		"actual_node_name": actual_node_name,
		"node_type": node_type,
		"parent_path": parent_path,
		"created_path": created_path,
		"name_collision_detected": (
			actual_node_name != node_name
		),
		"verified_exists": verified_exists,
		"undoable": true
	}


# ==========================================
# rename_node
# ==========================================


func rename_node_from_request(
	data: Dictionary
) -> Dictionary:

	if (
		not data.has("node_path")
		or not data.has("new_name")
	):

		return {
			"success": false,
			"error": (
				"rename_node requires node_path "
				+ "and new_name."
			)
		}

	var node_path: String = (
		str(data["node_path"])
	)

	if typeof(data["new_name"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"rename_node new_name must be "
				+ "a string."
			)
		}

	var new_name: String = (
		data["new_name"]
	)

	if new_name.strip_edges().is_empty():

		return {
			"success": false,
			"error": (
				"rename_node requires a non-empty "
				+ "new_name."
			)
		}

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	if target_node == edited_scene_root:

		return {
			"success": false,
			"error": (
				"Renaming the scene root is not "
				+ "currently supported."
			)
		}

	var old_name: String = (
		str(target_node.name)
	)

	undo_redo.create_action(
		"AI Agent: Rename "
		+ old_name
		+ " to "
		+ new_name
	)

	undo_redo.add_do_property(
		target_node,
		"name",
		new_name
	)

	undo_redo.add_undo_property(
		target_node,
		"name",
		old_name
	)

	undo_redo.commit_action()

	# --------------------------------------
	# Post-operation verification
	# --------------------------------------
	#
	# The "name" property setter has the same
	# silent auto-dedup behavior as add_child, so
	# we read the node's actual resulting name and
	# path back instead of assuming new_name stuck
	# exactly as requested.

	var actual_new_name: String = (
		str(target_node.name)
	)

	var node_path_after: String = (
		scene_helpers
		.get_relative_node_path(
			edited_scene_root,
			target_node
		)
	)

	var verify_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path_after
		)
	)

	var verified_exists: bool = (
		verify_result["success"]
	)

	return {
		"success": true,
		"action": "rename_node",
		"message": (
			"Node renamed successfully "
			+ "in the Godot editor."
		),
		"old_name": old_name,
		"new_name": new_name,
		"actual_new_name": actual_new_name,
		"node_path_before": node_path,
		"node_path_after": node_path_after,
		"name_collision_detected": (
			actual_new_name != new_name
		),
		"verified_exists": verified_exists,
		"undoable": true
	}


# ==========================================
# delete_node
# ==========================================


func delete_node_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"delete_node requires node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"])
	)

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	if target_node == edited_scene_root:

		return {
			"success": false,
			"error": (
				"Deleting the scene root is not "
				+ "allowed."
			)
		}

	var parent_node: Node = (
		target_node.get_parent()
	)

	if parent_node == null:

		return {
			"success": false,
			"error": (
				"Target node has no parent and "
				+ "cannot be deleted."
			)
		}

	var child_index: int = (
		target_node.get_index()
	)

	var target_name: String = (
		str(target_node.name)
	)

	# Owner preservation: the undo must restore the node's
	# ORIGINAL owner. Nodes inside an instanced sub-scene
	# are owned by the instance root, not the edited scene
	# root - blindly re-owning to the edited root on undo
	# converts instance-internal nodes into edited-scene
	# nodes and corrupts the saved scene.

	var original_owner: Node = (
		target_node.get_owner()
	)

	undo_redo.create_action(
		"AI Agent: Delete "
		+ target_name
	)

	undo_redo.add_do_method(
		parent_node,
		"remove_child",
		target_node
	)

	undo_redo.add_undo_method(
		parent_node,
		"add_child",
		target_node
	)

	undo_redo.add_undo_method(
		parent_node,
		"move_child",
		target_node,
		child_index
	)

	undo_redo.add_undo_method(
		target_node,
		"set_owner",
		original_owner
	)

	undo_redo.commit_action()

	# Post-mutation verification: the node must actually
	# be gone from its parent, and the parent index must
	# be back within bounds.

	var verified_deleted: bool = (
		parent_node.get_child_count() == 0
		or parent_node.get_child(
			mini(child_index, parent_node.get_child_count() - 1)
		) != target_node
	)

	var verified_absent: bool = (
		not edited_scene_root.is_ancestor_of(target_node)
		and target_node.get_parent() != parent_node
	)

	return {
		"success": verified_deleted and verified_absent,
		"action": "delete_node",
		"message": (
			"Node deleted successfully "
			+ "from the Godot editor."
			if verified_deleted and verified_absent
			else "Delete executed but verification "
			+ "could not confirm the removal."
		),
		"deleted_node": target_name,
		"node_path": node_path,
		"verified_deleted": verified_deleted,
		"verified_absent": verified_absent,
		"undoable": true
	}


# ==========================================
# reparent_node
# ==========================================


func reparent_node_from_request(
	data: Dictionary
) -> Dictionary:

	if (
		not data.has("node_path")
		or not data.has("new_parent_path")
	):

		return {
			"success": false,
			"error": (
				"reparent_node requires node_path "
				+ "and new_parent_path."
			)
		}

	var node_path: String = (
		str(data["node_path"])
	)

	var new_parent_path: String = (
		str(data["new_parent_path"])
	)

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	if target_node == edited_scene_root:

		return {
			"success": false,
			"error": (
				"Reparenting the scene root "
				+ "is not allowed."
			)
		}

	var parent_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			new_parent_path
		)
	)

	if not parent_result["success"]:

		return {
			"success": false,
			"error": (
				"New parent node not found: "
				+ new_parent_path
			)
		}

	var new_parent_node: Node = (
		parent_result["node"]
	)

	if target_node == new_parent_node:

		return {
			"success": false,
			"error": (
				"A node cannot be its own parent."
			)
		}

	if target_node.is_ancestor_of(
		new_parent_node
	):

		return {
			"success": false,
			"error": (
				"Cannot reparent a node under "
				+ "one of its own descendants."
			)
		}

	var old_parent_node: Node = (
		target_node.get_parent()
	)

	if old_parent_node == null:

		return {
			"success": false,
			"error": (
				"Target node has no current parent."
			)
		}

	var old_index: int = (
		target_node.get_index()
	)

	var target_name: String = (
		str(target_node.name)
	)

	# Owner preservation: a same-scene reparent keeps the
	# node's existing owner valid (the edited root remains
	# an ancestor), so owner is NOT rewritten - rewriting
	# it corrupts instance-internal nodes. Only a node
	# with no owner yet (never saved) gets claimed by the
	# edited scene. Undo restores the exact original.

	var original_owner: Node = (
		target_node.get_owner()
	)

	undo_redo.create_action(
		"AI Agent: Reparent "
		+ target_name
	)

	undo_redo.add_do_method(
		old_parent_node,
		"remove_child",
		target_node
	)

	undo_redo.add_do_method(
		new_parent_node,
		"add_child",
		target_node
	)

	if original_owner == null:

		undo_redo.add_do_method(
			target_node,
			"set_owner",
			edited_scene_root
		)

	undo_redo.add_undo_method(
		new_parent_node,
		"remove_child",
		target_node
	)

	undo_redo.add_undo_method(
		old_parent_node,
		"add_child",
		target_node
	)

	undo_redo.add_undo_method(
		old_parent_node,
		"move_child",
		target_node,
		old_index
	)

	undo_redo.add_undo_method(
		target_node,
		"set_owner",
		original_owner
	)

	undo_redo.commit_action()

	# --------------------------------------
	# Post-operation verification
	# --------------------------------------
	#
	# All three checks below are O(1)-ish: a
	# single targeted node lookup and two direct
	# reference comparisons against nodes we
	# already hold. None of this touches the wider
	# scene tree, and add_child's silent
	# auto-dedup rename (see create_node) applies
	# here too, so we read the node's real
	# resulting name/path back rather than
	# assuming it matches the request.

	var actual_node_name: String = (
		str(target_node.name)
	)

	var node_path_after: String = (
		scene_helpers
		.get_relative_node_path(
			edited_scene_root,
			target_node
		)
	)

	var old_parent_path: String = (
		scene_helpers
		.get_relative_node_path(
			edited_scene_root,
			old_parent_node
		)
	)

	var verify_new_parent_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path_after
		)
	)

	var verified_new_parent: bool = (
		verify_new_parent_result["success"]
	)

	var verified_old_parent_absent: bool = (
		target_node.get_parent()
		!= old_parent_node
	)

	return {
		"success": true,
		"action": "reparent_node",
		"message": (
			"Node reparented successfully "
			+ "in the Godot editor."
		),
		"node_name": target_name,
		"actual_node_name": actual_node_name,
		"node_path_before": node_path,
		"old_parent_path": old_parent_path,
		"new_parent_path": new_parent_path,
		"node_path_after": node_path_after,
		"name_collision_detected": (
			actual_node_name != target_name
		),
		"verified_new_parent": verified_new_parent,
		"verified_old_parent_absent": (
			verified_old_parent_absent
		),
		"undoable": true
	}


# ==========================================
# move_child
# ==========================================
# Moves an existing child within its parent to a
# requested sibling index as one undoable
# EditorUndoRedoManager action. The result reports
# the real sibling order read back from the scene
# after the move (never fabricated).


func move_child_from_request(
	data: Dictionary
) -> Dictionary:

	if (
		not data.has("node_path")
		or not data.has("new_index")
	):

		return {
			"success": false,
			"error": (
				"move_child requires node_path "
				+ "and new_index."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var raw_index = data["new_index"]

	if (
		typeof(raw_index) != TYPE_INT
		and typeof(raw_index) != TYPE_FLOAT
	):

		return {
			"success": false,
			"error": (
				"move_child new_index must be "
				+ "an integer sibling index."
			)
		}

	var new_index := int(raw_index)

	if (
		float(raw_index) != float(new_index)
	):

		return {
			"success": false,
			"error": (
				"move_child new_index must be "
				+ "an integer sibling index."
			)
		}

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	var target_name: String = (
		str(target_node.name)
	)

	if target_node == edited_scene_root:

		return {
			"success": false,
			"error": (
				"Moving the scene root is not "
				+ "allowed."
			)
		}

	var parent_node: Node = (
		target_node.get_parent()
	)

	if parent_node == null:

		return {
			"success": false,
			"error": (
				"Target node has no parent and "
				+ "cannot be moved."
			)
		}

	var old_index: int = (
		target_node.get_index()
	)

	var child_count: int = (
		parent_node.get_child_count()
	)

	if (
		new_index < 0
		or new_index >= child_count
	):

		return {
			"success": false,
			"error": (
				"move_child new_index "
				+ str(new_index)
				+ " is out of range: the parent "
				+ str(scene_helpers
					.get_relative_node_path(
						edited_scene_root,
						parent_node
					))
				+ " has "
				+ str(child_count)
				+ " child(ren); valid indices "
				+ "are 0 to "
				+ str(child_count - 1)
				+ "."
			)
		}

	var sibling_order_before: Array = []
	for child in parent_node.get_children():
		sibling_order_before.append(
			str(child.name)
		)

	# --------------------------------------
	# Deterministic no-op handling
	# --------------------------------------
	# Already at the requested index: no undo
	# history is created and nothing changes.
	# The reported order is still verified
	# against the actual scene state.

	if new_index == old_index:

		return {
			"success": true,
			"action": "move_child",
			"message": (
				"Node is already at sibling "
				+ "index "
				+ str(new_index)
				+ "; no move was performed."
			),
			"node_path": node_path,
			"node_name": target_name,
			"requested_index": new_index,
			"old_index": old_index,
			"new_index": new_index,
			"moved": false,
			"parent_path": (
				scene_helpers
				.get_relative_node_path(
					edited_scene_root,
					parent_node
				)
			),
			"sibling_order_before": (
				sibling_order_before
			),
			"sibling_order_after": (
				sibling_order_before.duplicate()
			),
			"verified_index": true,
			"verified_order": true,
			"undoable": false
		}

	# The editor undo manager is only available
	# inside the running editor; a headless
	# SceneTree process reports an explicit
	# unavailable error instead of crashing or
	# mutating without undo support.

	if undo_redo == null:

		return {
			"success": false,
			"action": "move_child",
			"error": (
				"move_child requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	undo_redo.create_action(
		"AI Agent: Move "
		+ target_name
		+ " to index "
		+ str(new_index)
	)

	undo_redo.add_do_method(
		parent_node,
		"move_child",
		target_node,
		new_index
	)

	undo_redo.add_undo_method(
		parent_node,
		"move_child",
		target_node,
		old_index
	)

	undo_redo.commit_action()

	# --------------------------------------
	# Post-operation verification
	# --------------------------------------
	# Read the real resulting index and the
	# real sibling order back from the scene.
	# The expected order is computed by
	# simulating the move on the recorded
	# before-order, so verified_order compares
	# actual scene state against the move
	# semantics, not against the request.

	var verified_index: bool = (
		target_node.get_index() == new_index
	)

	var sibling_order_after: Array = []
	for child in parent_node.get_children():
		sibling_order_after.append(
			str(child.name)
		)

	var expected_order: Array = (
		sibling_order_before.duplicate()
	)
	expected_order.remove_at(old_index)
	expected_order.insert(
		new_index,
		target_name
	)

	var verified_order: bool = (
		sibling_order_after == expected_order
	)

	return {
		"success": true,
		"action": "move_child",
		"message": (
			"Node moved successfully "
			+ "in the Godot editor."
		),
		"node_path": node_path,
		"node_name": target_name,
		"requested_index": new_index,
		"old_index": old_index,
		"new_index": (
			target_node.get_index()
		),
		"moved": true,
		"parent_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				parent_node
			)
		),
		"sibling_order_before": (
			sibling_order_before
		),
		"sibling_order_after": (
			sibling_order_after
		),
		"verified_index": verified_index,
		"verified_order": verified_order,
		"undoable": true
	}


# ==========================================
# add_to_group / remove_from_group
# ==========================================
# Group membership mutations for a node in the
# currently edited scene. Each change is one
# undoable EditorUndoRedoManager action. Membership
# is read back from the node's real instance state
# (is_in_group) after the mutation and reported as
# verified membership; verification is never
# fabricated.
#
# Idempotent cases (adding a node that is already a
# member, removing a node that is not a member) are
# deterministic successes with no scene change and
# no undo history.


func _validate_group_mutation_request(
	data: Dictionary,
	action_name: String
) -> Dictionary:
	# Shared request validation for both group
	# mutations. Returns {"ok": true, "group_name": ...}
	# or a structured failure result.

	if not data.has("group_name"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires group_name."
			)
		}

	var raw_group = data["group_name"]

	if typeof(raw_group) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				action_name
				+ " group_name must be a "
				+ "string."
			)
		}

	var group_name: String = (
		str(raw_group).strip_edges()
	)

	if group_name.is_empty():

		return {
			"success": false,
			"error": (
				action_name
				+ " requires a non-empty "
				+ "group_name."
			)
		}

	return {
		"ok": true,
		"group_name": group_name
	}


func add_to_group_from_request(
	data: Dictionary
) -> Dictionary:

	var validation := (
		_validate_group_mutation_request(
			data,
			"add_to_group"
		)
	)

	if not validation.get("ok", false):
		return validation

	var group_name: String = (
		validation["group_name"]
	)

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"add_to_group requires node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var target_node: Node = (
		node_result["node"]
	)

	var target_name: String = (
		str(target_node.name)
	)

	var was_member: bool = (
		target_node.is_in_group(group_name)
	)

	# Deterministic idempotent case: already a
	# member. No duplicate state, no undo history,
	# membership still verified against the node.

	if was_member:

		return {
			"success": true,
			"action": "add_to_group",
			"message": (
				"Node is already in group "
				+ group_name
				+ "; no change was made."
			),
			"node_path": node_path,
			"node_name": target_name,
			"group_name": group_name,
			"was_member": true,
			"is_member": true,
			"changed": false,
			"verified_membership": true,
			"undoable": false
		}

	# The editor undo manager is only available
	# inside the running editor; a headless
	# SceneTree process reports an explicit
	# unavailable error instead of mutating
	# without undo support.

	if undo_redo == null:

		return {
			"success": false,
			"action": "add_to_group",
			"error": (
				"add_to_group requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	undo_redo.create_action(
		"AI Agent: Add "
		+ target_name
		+ " to group "
		+ group_name
	)

	undo_redo.add_do_method(
		target_node,
		"add_to_group",
		group_name
	)

	undo_redo.add_undo_method(
		target_node,
		"remove_from_group",
		group_name
	)

	undo_redo.commit_action()

	# Post-mutation verification: read the real
	# membership back from the node.

	var is_member: bool = (
		target_node.is_in_group(group_name)
	)

	return {
		"success": true,
		"action": "add_to_group",
		"message": (
			"Node added to group successfully "
			+ "in the Godot editor."
		),
		"node_path": node_path,
		"node_name": target_name,
		"group_name": group_name,
		"was_member": false,
		"is_member": is_member,
		"changed": true,
		"verified_membership": is_member,
		"undoable": true
	}


func remove_from_group_from_request(
	data: Dictionary
) -> Dictionary:

	var validation := (
		_validate_group_mutation_request(
			data,
			"remove_from_group"
		)
	)

	if not validation.get("ok", false):
		return validation

	var group_name: String = (
		validation["group_name"]
	)

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"remove_from_group requires node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var target_node: Node = (
		node_result["node"]
	)

	var target_name: String = (
		str(target_node.name)
	)

	var was_member: bool = (
		target_node.is_in_group(group_name)
	)

	# Deterministic idempotent case: not a member.
	# No scene change, no undo history, membership
	# still verified against the node.

	if not was_member:

		return {
			"success": true,
			"action": "remove_from_group",
			"message": (
				"Node is not in group "
				+ group_name
				+ "; no change was made."
			),
			"node_path": node_path,
			"node_name": target_name,
			"group_name": group_name,
			"was_member": false,
			"is_member": false,
			"changed": false,
			"verified_membership": true,
			"undoable": false
		}

	if undo_redo == null:

		return {
			"success": false,
			"action": "remove_from_group",
			"error": (
				"remove_from_group requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	undo_redo.create_action(
		"AI Agent: Remove "
		+ target_name
		+ " from group "
		+ group_name
	)

	undo_redo.add_do_method(
		target_node,
		"remove_from_group",
		group_name
	)

	undo_redo.add_undo_method(
		target_node,
		"add_to_group",
		group_name
	)

	undo_redo.commit_action()

	var is_member: bool = (
		target_node.is_in_group(group_name)
	)

	return {
		"success": true,
		"action": "remove_from_group",
		"message": (
			"Node removed from group successfully "
			+ "in the Godot editor."
		),
		"node_path": node_path,
		"node_name": target_name,
		"group_name": group_name,
		"was_member": true,
		"is_member": is_member,
		"changed": true,
		"verified_membership": is_member == false,
		"undoable": true
	}


# ==========================================
# Signal connections
# ==========================================
# Signal-connection tools for the currently edited
# scene: one read-only inspector for live connection
# state, plus two mutations (connect_signal,
# disconnect_signal) performed as editor-native,
# undoable EditorUndoRedoManager actions with
# read-back verification.
#
# Connections are addressed exactly like the editor's
# Connect dialog: emitter node path + signal name ->
# target node path + method name. Callable
# expressions and bound arguments are deliberately
# not supported: the connection identity must stay
# deterministic and JSON-safe.


func _validate_signal_mutation_request(
	data: Dictionary,
	action_name: String
) -> Dictionary:
	# Shared request validation for both signal
	# mutations. Returns {"ok": true, ...} or a
	# structured failure result.

	var required_string_fields := [
		"signal_name",
		"target_path",
		"method_name",
	]

	var validated := {
		"ok": true
	}

	for field_name in required_string_fields:

		if not data.has(field_name):

			return {
				"success": false,
				"error": (
					action_name
					+ " requires "
					+ field_name
					+ "."
				)
			}

		var raw_value = data[field_name]

		if typeof(raw_value) != TYPE_STRING:

			return {
				"success": false,
				"error": (
					action_name
					+ " "
					+ field_name
					+ " must be a string."
				)
			}

		var value: String = (
			str(raw_value).strip_edges()
		)

		if value.is_empty():

			return {
				"success": false,
				"error": (
					action_name
					+ " requires a non-empty "
					+ field_name
					+ "."
				)
			}

		validated[field_name] = value

	return validated


func list_node_connections_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"list_node_connections requires "
				+ "node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	if node_path.is_empty():

		return {
			"success": false,
			"error": (
				"list_node_connections requires a "
				+ "non-empty node_path (use \".\" "
				+ "for the edited scene root)."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	# Connection flags are serialized as plain
	# booleans so the result stays JSON-safe and
	# deterministic.

	# Editor plumbing and other peers outside the edited
	# scene (e.g. SceneTreeEditor hooks into script_changed)
	# are omitted from the entries and reported only as a
	# count: the bridge operates exclusively inside the
	# edited scene, and unpersisted editor hooks are noise
	# for agent reasoning. Nothing is silently hidden.

	var internal_omitted: int = 0

	var incoming: Array = []

	for raw_connection in (
		target_node.get_incoming_connections()
	):

		# Type-check Variants before any typed
		# assignment: a malformed connection entry
		# is skipped, never a script error.
		#
		# get_incoming_connections() names the
		# receiving callable "method" in early 4.x
		# releases and "callable" in later ones, so
		# accept either key.

		var raw_incoming_signal: Variant = (
			raw_connection.get("signal")
		)

		var raw_incoming_callable: Variant = (
			raw_connection.get("callable")
		)

		if not (raw_incoming_callable is Callable):

			raw_incoming_callable = (
				raw_connection.get("method")
			)

		if not (raw_incoming_signal is Signal):
			continue

		if not (raw_incoming_callable is Callable):
			continue

		var incoming_signal: Signal = (
			raw_incoming_signal
		)

		var incoming_callable: Callable = (
			raw_incoming_callable
		)

		var raw_source_node: Variant = (
			incoming_signal.get_object()
		)

		if not raw_source_node is Node:
			continue

		var source_node: Node = raw_source_node

		if source_node != edited_scene_root \
				and not edited_scene_root.is_ancestor_of(
					source_node
				):

			internal_omitted += 1

			continue

		var flags: int = int(
			raw_connection.get("flags", 0)
		)

		incoming.append(
			{
				"signal": str(
					incoming_signal.get_name()
				),
				"source": (
					scene_helpers
					.get_relative_node_path(
						edited_scene_root,
						source_node
					)
				),
				"source_name": (
					str(source_node.name)
				),
				"method": str(
					incoming_callable.get_method()
				),
				"deferred": (
					flags & CONNECT_DEFERRED
				) != 0,
				"persistent": (
					flags & CONNECT_PERSIST
				) != 0,
				"one_shot": (
					flags & CONNECT_ONE_SHOT
				) != 0,
			}
		)

	var outgoing: Array = []

	for raw_signal in target_node.get_signal_list():

		var signal_name: String = str(
			raw_signal.get("name", "")
		)

		if signal_name.is_empty():
			continue

		for raw_connection in (
			target_node.get_signal_connection_list(
				signal_name
			)
		):

			var raw_outgoing_callable: Variant = (
				raw_connection.get("callable")
			)

			if not (raw_outgoing_callable is Callable):
				continue

			var outgoing_callable: Callable = (
				raw_outgoing_callable
			)

			var raw_peer_node: Variant = (
				outgoing_callable.get_object()
			)

			if not raw_peer_node is Node:
				continue

			var peer_node: Node = raw_peer_node

			if peer_node != edited_scene_root \
					and not edited_scene_root.is_ancestor_of(
						peer_node
					):

				internal_omitted += 1

				continue

			var flags: int = int(
				raw_connection.get("flags", 0)
			)

			outgoing.append(
				{
					"signal": signal_name,
					"target": (
						scene_helpers
						.get_relative_node_path(
							edited_scene_root,
							peer_node
						)
					),
					"target_name": (
						str(peer_node.name)
					),
					"method": str(
						outgoing_callable.get_method()
					),
					"deferred": (
						flags & CONNECT_DEFERRED
					) != 0,
					"persistent": (
						flags & CONNECT_PERSIST
					) != 0,
					"one_shot": (
						flags & CONNECT_ONE_SHOT
					) != 0,
				}
			)

	# Deterministic ordering: by signal name, then
	# peer path, then method name.

	incoming.sort_custom(
		func(a, b):
			if a["signal"] != b["signal"]:
				return a["signal"] < b["signal"]
			if a["source"] != b["source"]:
				return a["source"] < b["source"]
			return a["method"] < b["method"]
	)

	outgoing.sort_custom(
		func(a, b):
			if a["signal"] != b["signal"]:
				return a["signal"] < b["signal"]
			if a["target"] != b["target"]:
				return a["target"] < b["target"]
			return a["method"] < b["method"]
	)

	return {
		"success": true,
		"action": "list_node_connections",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": (
			str(target_node.name)
		),
		"node_type": (
			target_node.get_class()
		),
		"total_incoming": incoming.size(),
		"total_outgoing": outgoing.size(),
		"internal_connections_omitted": internal_omitted,
		"incoming": incoming,
		"outgoing": outgoing,
	}


func _resolve_connection_nodes(
	data: Dictionary,
	action_name: String
) -> Dictionary:
	# Shared node resolution for both signal mutations.
	# Returns {"ok": true, ...} with the emitter node,
	# the target node, and the validated strings, or a
	# structured failure result.

	var validation := (
		_validate_signal_mutation_request(
			data,
			action_name
		)
	)

	if not validation.get("ok", false):
		return validation

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				action_name
				+ " requires node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	var emitter_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not emitter_result["success"]:
		return emitter_result

	var target_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			validation["target_path"]
		)
	)

	if not target_result["success"]:
		return target_result

	var emitter_node: Node = (
		emitter_result["node"]
	)

	var target_node: Node = (
		target_result["node"]
	)

	var signal_name: String = (
		validation["signal_name"]
	)

	var method_name: String = (
		validation["method_name"]
	)

	# The bridge is the authoritative environment for
	# validating Godot wiring: never connect a signal
	# that does not exist or a method that cannot be
	# called. DISCONNECT deliberately skips these gates:
	# its whole purpose is removing stale connections
	# whose signal or method no longer exists after a
	# script edit.

	if action_name != "disconnect_signal":

		if not emitter_node.has_signal(signal_name):

			return {
				"success": false,
				"error": (
					action_name + ": node "
					+ str(emitter_node.name)
					+ " has no signal named "
					+ signal_name
					+ ". Use list_node_signals to "
					+ "discover valid signal names."
				)
			}

		if not target_node.has_method(method_name):

			return {
				"success": false,
				"error": (
					action_name + ": node "
					+ str(target_node.name)
					+ " has no method named "
					+ method_name
					+ "."
				)
			}

	return {
		"ok": true,
		"emitter_node": emitter_node,
		"target_node": target_node,
		"node_path": node_path,
		"signal_name": signal_name,
		"target_path": validation["target_path"],
		"method_name": method_name,
	}


func connect_signal_from_request(
	data: Dictionary
) -> Dictionary:

	var resolved := (
		_resolve_connection_nodes(
			data,
			"connect_signal"
		)
	)

	if not resolved.get("ok", false):
		return resolved

	# Deferred connections are opt-in; anything other
	# than a real boolean is a request error, not a
	# silent default.

	var deferred: bool = false

	if data.has("deferred"):

		if typeof(data["deferred"]) != TYPE_BOOL:

			return {
				"success": false,
				"error": (
					"connect_signal deferred must "
					+ "be a boolean."
				)
			}

		deferred = data["deferred"]

	var emitter_node: Node = (
		resolved["emitter_node"]
	)

	var target_node: Node = (
		resolved["target_node"]
	)

	var signal_name: String = (
		resolved["signal_name"]
	)

	var method_name: String = (
		resolved["method_name"]
	)

	var callable: Callable = Callable(
		target_node,
		method_name
	)

	var was_connected: bool = (
		emitter_node.is_connected(
			signal_name,
			callable
		)
	)

	var emitter_name: String = (
		str(emitter_node.name)
	)

	var target_name: String = (
		str(target_node.name)
	)

	# Deterministic idempotent case: already
	# connected. No duplicate connection, no undo
	# history, connection still verified against the
	# emitter.

	if was_connected:

		return {
			"success": true,
			"action": "connect_signal",
			"message": (
				"Signal is already connected; "
				+ "no change was made."
			),
			"node_path": resolved["node_path"],
			"node_name": emitter_name,
			"signal_name": signal_name,
			"target_path": resolved["target_path"],
			"target_name": target_name,
			"method_name": method_name,
			"deferred": deferred,
			"was_connected": true,
			"is_connected": true,
			"changed": false,
			"verified_connection": true,
			"undoable": false
		}

	# The editor undo manager is only available
	# inside the running editor; a headless
	# SceneTree process reports an explicit
	# unavailable error instead of mutating
	# without undo support.

	if undo_redo == null:

		return {
			"success": false,
			"action": "connect_signal",
			"error": (
				"connect_signal requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	# Editor-native connections are persistent so the
	# wiring is saved with the scene, matching what
	# the editor's Connect dialog produces.

	var connect_flags: int = CONNECT_PERSIST

	if deferred:

		connect_flags |= CONNECT_DEFERRED

	undo_redo.create_action(
		"AI Agent: Connect "
		+ emitter_name
		+ "."
		+ signal_name
		+ " to "
		+ target_name
		+ "."
		+ method_name
	)

	undo_redo.add_do_method(
		emitter_node,
		"connect",
		signal_name,
		callable,
		connect_flags
	)

	undo_redo.add_undo_method(
		emitter_node,
		"disconnect",
		signal_name,
		callable
	)

	undo_redo.commit_action()

	# Post-mutation verification: read the real
	# connection state back from the emitter.

	var is_connected: bool = (
		emitter_node.is_connected(
			signal_name,
			callable
		)
	)

	return {
		"success": true,
		"action": "connect_signal",
		"message": (
			"Signal connected successfully "
			+ "in the Godot editor."
		),
		"node_path": resolved["node_path"],
		"node_name": emitter_name,
		"signal_name": signal_name,
		"target_path": resolved["target_path"],
		"target_name": target_name,
		"method_name": method_name,
		"deferred": deferred,
		"was_connected": false,
		"is_connected": is_connected,
		"changed": true,
		"verified_connection": is_connected,
		"undoable": true
	}


func disconnect_signal_from_request(
	data: Dictionary
) -> Dictionary:

	var resolved := (
		_resolve_connection_nodes(
			data,
			"disconnect_signal"
		)
	)

	if not resolved.get("ok", false):
		return resolved

	var emitter_node: Node = (
		resolved["emitter_node"]
	)

	var target_node: Node = (
		resolved["target_node"]
	)

	var signal_name: String = (
		resolved["signal_name"]
	)

	var method_name: String = (
		resolved["method_name"]
	)

	var callable: Callable = Callable(
		target_node,
		method_name
	)

	var was_connected: bool = (
		emitter_node.is_connected(
			signal_name,
			callable
		)
	)

	var emitter_name: String = (
		str(emitter_node.name)
	)

	var target_name: String = (
		str(target_node.name)
	)

	# Deterministic idempotent case: not connected.
	# No scene change, no undo history, state still
	# verified against the emitter.

	if not was_connected:

		return {
			"success": true,
			"action": "disconnect_signal",
			"message": (
				"Signal is not connected; "
				+ "no change was made."
			),
			"node_path": resolved["node_path"],
			"node_name": emitter_name,
			"signal_name": signal_name,
			"target_path": resolved["target_path"],
			"target_name": target_name,
			"method_name": method_name,
			"was_connected": false,
			"is_connected": false,
			"changed": false,
			"verified_connection": true,
			"undoable": false
		}

	if undo_redo == null:

		return {
			"success": false,
			"action": "disconnect_signal",
			"error": (
				"disconnect_signal requires the plugin-owned "
				+ "EditorUndoRedoManager, which is only "
				+ "available inside the running Godot "
				+ "editor."
			)
		}

	# Undo must restore the original connection, so
	# capture the real flags of the existing
	# connection before removing it.

	var original_flags: int = CONNECT_PERSIST

	for raw_connection in (
		emitter_node.get_signal_connection_list(
			signal_name
		)
	):

		var existing: Variant = (
			raw_connection.get("callable")
		)

		if not (existing is Callable):
			continue

		if existing == callable:

			original_flags = int(
				raw_connection.get(
					"flags",
					CONNECT_PERSIST
				)
			)

			break

	undo_redo.create_action(
		"AI Agent: Disconnect "
		+ emitter_name
		+ "."
		+ signal_name
		+ " from "
		+ target_name
		+ "."
		+ method_name
	)

	undo_redo.add_do_method(
		emitter_node,
		"disconnect",
		signal_name,
		callable
	)

	undo_redo.add_undo_method(
		emitter_node,
		"connect",
		signal_name,
		callable,
		original_flags
	)

	undo_redo.commit_action()

	var is_connected: bool = (
		emitter_node.is_connected(
			signal_name,
			callable
		)
	)

	return {
		"success": true,
		"action": "disconnect_signal",
		"message": (
			"Signal disconnected successfully "
			+ "in the Godot editor."
		),
		"node_path": resolved["node_path"],
		"node_name": emitter_name,
		"signal_name": signal_name,
		"target_path": resolved["target_path"],
		"target_name": target_name,
		"method_name": method_name,
		"was_connected": true,
		"is_connected": is_connected,
		"changed": true,
		"verified_connection": is_connected == false,
		"undoable": true
	}


# ==========================================
# duplicate_node
# ==========================================


func duplicate_node_from_request(
	data: Dictionary
) -> Dictionary:

	if (
		not data.has("node_path")
		or not data.has("new_parent_path")
		or not data.has("new_name")
	):

		return {
			"success": false,
			"error": (
				"duplicate_node requires node_path, "
				+ "new_parent_path, and new_name."
			)
		}

	var node_path: String = (
		str(data["node_path"])
	)

	var new_parent_path: String = (
		str(data["new_parent_path"])
	)

	if typeof(data["new_name"]) != TYPE_STRING:

		return {
			"success": false,
			"error": (
				"duplicate_node new_name must be "
				+ "a string."
			)
		}

	var new_name: String = (
		data["new_name"]
	)

	if new_name.strip_edges().is_empty():

		return {
			"success": false,
			"error": (
				"duplicate_node requires a non-empty "
				+ "new_name."
			)
		}

	var node_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var source_node: Node = (
		node_result["node"]
	)

	if source_node == edited_scene_root:

		return {
			"success": false,
			"error": (
				"Duplicating the scene root is not "
				+ "currently supported."
			)
		}

	var parent_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			new_parent_path
		)
	)

	if not parent_result["success"]:

		return {
			"success": false,
			"error": (
				"New parent node not found: "
				+ new_parent_path
			)
		}

	var new_parent_node: Node = (
		parent_result["node"]
	)

	if source_node == new_parent_node:

		return {
			"success": false,
			"error": (
				"A node cannot be duplicated "
				+ "under itself."
			)
		}

	if source_node.is_ancestor_of(
		new_parent_node
	):

		return {
			"success": false,
			"error": (
				"Cannot duplicate a node under "
				+ "one of its own descendants."
			)
		}

	var source_name: String = (
		str(source_node.name)
	)

	# Node.duplicate() returns a detached copy
	# that is NOT yet part of the scene tree.
	var duplicated_node: Node = (
		source_node.duplicate()
	)

	duplicated_node.name = new_name

	undo_redo.create_action(
		"AI Agent: Duplicate "
		+ source_name
	)

	# add_child attaches the duplicate to the
	# destination parent. set_owner is applied
	# recursively to the entire duplicated
	# subtree so every descendant is owned by
	# the edited scene root.
	undo_redo.add_do_method(
		new_parent_node,
		"add_child",
		duplicated_node
	)

	undo_redo.add_do_method(
		self,
		"_set_owner_recursive",
		duplicated_node,
		edited_scene_root
	)

	undo_redo.add_undo_method(
		new_parent_node,
		"remove_child",
		duplicated_node
	)

	undo_redo.commit_action()

	# --------------------------------------
	# Post-operation verification
	# --------------------------------------
	#
	# add_child silently renames the new child
	# if a sibling already has the same name,
	# so we read the node's actual resulting
	# name and path back instead of assuming it
	# matches the request.

	var actual_node_name: String = (
		str(duplicated_node.name)
	)

	var node_path_after: String = (
		scene_helpers
		.get_relative_node_path(
			edited_scene_root,
			duplicated_node
		)
	)

	var verify_result: Dictionary = (
		scene_helpers
		.resolve_node_or_error(
			node_path_after
		)
	)

	var verified_exists: bool = (
		verify_result["success"]
	)

	var verified_owned = duplicated_node.get_owner() == edited_scene_root

	return {
		"success": true,
		"action": "duplicate_node",
		"message": (
			"Node duplicated successfully "
			+ "in the Godot editor."
		),
		"node_name": new_name,
		"actual_node_name": actual_node_name,
		"node_path_before": node_path,
		"new_parent_path": new_parent_path,
		"node_path_after": node_path_after,
		"name_collision_detected": (
			actual_node_name != new_name
		),
		"verified_exists": verified_exists,
		"verified_owned": verified_owned,
		"undoable": true
	}


# ==========================================
# Ownership helper
# ==========================================
#
# Node.duplicate() does not automatically
# set the owner of the duplicated subtree
# to the edited scene root. Without this,
# the duplicated nodes would not be saved
# with the scene. This helper walks the
# entire duplicated subtree and sets the
# owner of every Node descendant to the
# edited scene root, matching the project's
# existing ownership convention used by
# create_node and reparent_node.


func _set_owner_recursive(
	target_node: Node,
	new_owner: Node
) -> void:

	target_node.set_owner(
		new_owner
	)

	for child in target_node.get_children():

		if child is Node:

			child.set_owner(
				new_owner
			)

			_set_owner_recursive(
				child,
				new_owner
			)


# ==========================================
# validate_node_type
# ==========================================
# Read-only pre-flight check for node-type
# dependent operations such as create_node.
# Answers from the actual ClassDB of the
# running editor. No scene state is read or
# modified.


func validate_node_type_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_type"):

		return {
			"success": false,
			"error": (
				"validate_node_type requires node_type."
			)
		}

	var node_type: String = (
		str(data["node_type"]).strip_edges()
	)

	if node_type.is_empty():

		return {
			"success": false,
			"error": (
				"validate_node_type requires a "
				+ "non-empty node_type."
			)
		}

	var type_exists: bool = (
		ClassDB.class_exists(node_type)
	)

	# "Node" itself is a valid parent class, so
	# any Node subclass (including Node) passes.
	var is_node_class: bool = (
		type_exists
		and ClassDB.is_parent_class(
			node_type,
			"Node"
		)
	)

	# Abstract base classes such as CanvasItem
	# exist and inherit from Node but cannot be
	# instantiated directly, so they are not
	# valid targets for create_node.
	var can_instantiate: bool = (
		type_exists
		and ClassDB.can_instantiate(node_type)
	)

	var parent_class: String = ""

	if type_exists:

		parent_class = str(
			ClassDB.get_parent_class(node_type)
		)

	var is_valid: bool = (
		type_exists
		and is_node_class
		and can_instantiate
	)

	var message: String

	if not type_exists:

		message = (
			"'"
			+ node_type
			+ "' is not a registered Godot class."
		)

	elif not is_node_class:

		message = (
			"'"
			+ node_type
			+ "' exists but is not a Node class."
		)

	elif not can_instantiate:

		message = (
			"'"
			+ node_type
			+ "' is a Node class but cannot be "
			+ "instantiated directly."
		)

	else:

		message = (
			"'"
			+ node_type
			+ "' is a valid, instantiable node type."
		)

	return {
		"success": true,
		"action": "validate_node_type",
		"node_type": node_type,
		"valid": is_valid,
		"exists": type_exists,
		"is_node_class": is_node_class,
		"can_instantiate": can_instantiate,
		"parent_class": parent_class,
		"message": message
	}


# ==========================================
# get_node_class_info
# ==========================================
# Read-only ClassDB lookup for a single class.
# Returns the class name, its base class, and whether
# it can be instantiated directly. No scene state is
# read or modified.


func get_node_class_info_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("class_name"):

		return {
			"success": false,
			"error": (
				"get_node_class_info requires class_name."
			)
		}

	var requested_class_name: String = (
		str(data["class_name"]).strip_edges()
	)

	if requested_class_name.is_empty():

		return {
			"success": false,
			"error": (
				"get_node_class_info requires a "
				+ "non-empty class_name."
			)
		}

	var class_exists: bool = (
		ClassDB.class_exists(requested_class_name)
	)

	if not class_exists:

		return {
			"success": false,
			"error": (
				"'"
				+ requested_class_name
				+ "' is not a registered Godot class."
			)
		}

	var base_class: String = str(
		ClassDB.get_parent_class(requested_class_name)
	)

	var can_instantiate: bool = (
		ClassDB.can_instantiate(requested_class_name)
	)

	return {
		"success": true,
		"action": "get_node_class_info",
		"class_name": requested_class_name,
		"base_class": base_class,
		"can_instantiate": can_instantiate
	}


# ==========================================
# list_available_node_types
# ==========================================
# Bounded ClassDB discovery for native,
# instantiable Node classes. This is read-only
# and intentionally returns names only; callers
# use validate_node_type for an exact candidate.


func list_available_node_types_from_request(
	data: Dictionary
) -> Dictionary:

	var inherits_from := ""
	var name_contains := ""
	var limit := DEFAULT_NODE_TYPE_RESULT_LIMIT

	if (
		data.has("inherits_from")
		and data["inherits_from"] != null
	):

		inherits_from = str(
			data["inherits_from"]
		).strip_edges()

		if inherits_from.is_empty():

			return {
				"success": false,
				"error": (
					"list_available_node_types inherits_from "
					+ "must be non-empty when provided."
				)
			}

		if not ClassDB.class_exists(inherits_from):

			return {
				"success": false,
				"error": (
					"Invalid inherits_from filter: "
					+ inherits_from
					+ " is not a registered Godot class."
				)
			}

		if not ClassDB.is_parent_class(
			inherits_from,
			"Node"
		):

			return {
				"success": false,
				"error": (
					"Invalid inherits_from filter: "
					+ inherits_from
					+ " is not a Node class."
				)
			}

	if (
		data.has("name_contains")
		and data["name_contains"] != null
	):

		name_contains = str(
			data["name_contains"]
		).strip_edges()

		if name_contains.is_empty():

			return {
				"success": false,
				"error": (
					"list_available_node_types name_contains "
					+ "must be non-empty when provided."
				)
			}

	if (
		data.has("limit")
		and data["limit"] != null
	):

		var supplied_limit = data["limit"]

		if (
			typeof(supplied_limit) != TYPE_INT
			and typeof(supplied_limit) != TYPE_FLOAT
		):

			return _node_type_limit_error()

		limit = int(supplied_limit)

		if (
			float(supplied_limit) != float(limit)
			or limit < 1
			or limit > MAX_NODE_TYPE_RESULT_LIMIT
		):

			return _node_type_limit_error()

	var matching_types: Array = []

	for class_name_variant in ClassDB.get_class_list():

		var candidate_name := str(class_name_variant)

		if not ClassDB.is_parent_class(
			candidate_name,
			"Node"
		):

			continue

		if not ClassDB.can_instantiate(candidate_name):

			continue

		if (
			not inherits_from.is_empty()
			and candidate_name != inherits_from
			and not ClassDB.is_parent_class(
				candidate_name,
				inherits_from
			)
		):

			continue

		if (
			not name_contains.is_empty()
			and not candidate_name.to_lower().contains(
				name_contains.to_lower()
			)
		):

			continue

		matching_types.append(candidate_name)

	matching_types.sort()

	var total_matches := matching_types.size()
	var node_types: Array = []

	for index in range(min(limit, total_matches)):
		node_types.append(matching_types[index])

	return {
		"success": true,
		"action": "list_available_node_types",
		"inherits_from": inherits_from,
		"name_contains": name_contains,
		"limit": limit,
		"total_matches": total_matches,
		"truncated": total_matches > limit,
		"node_types": node_types
	}


func _node_type_limit_error() -> Dictionary:

	return {
		"success": false,
		"error": (
			"list_available_node_types limit must be an "
			+ "integer from 1 to "
			+ str(MAX_NODE_TYPE_RESULT_LIMIT)
			+ "."
		)
	}
# ==========================================
# list_node_signals
# ==========================================
# Read-only signal inspection for a single node in
# the currently edited scene. The result comes from
# the node's real reflection data (Node.get_signal_list()),
# which includes built-in and inherited signals. No scene
# state is read beyond node resolution or modified.


func list_node_signals_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"list_node_signals requires "
				+ "node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	if node_path.is_empty():

		return {
			"success": false,
			"error": (
				"list_node_signals requires a "
				+ "non-empty node_path (use \".\" "
				+ "for the edited scene root)."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	# Node.get_signal_list() is the authoritative
	# Godot reflection source: it returns every
	# signal available on the node, including
	# built-in and inherited ones. Only stable,
	# JSON-safe fields are serialized, and the
	# list is sorted by signal name so results
	# are deterministic.
	var raw_signals: Array = (
		target_node.get_signal_list()
	)

	var signals: Array = []

	for raw_signal in raw_signals:

		var signal_args: Array = []

		for raw_arg in (
			raw_signal.get("args", [])
		):

			var arg_type := int(
				raw_arg.get(
					"type",
					TYPE_NIL
				)
			)

			signal_args.append(
				{
					"name": str(
						raw_arg.get(
							"name",
							""
						)
					),
					"type": type_string(
						arg_type
					),
					"type_id": arg_type,
				}
			)

		signals.append(
			{
				"name": str(
					raw_signal.get(
						"name",
						""
					)
				),
				"args": signal_args,
			}
		)

	signals.sort_custom(
		func(a, b): return a["name"] < b["name"]
	)

	return {
		"success": true,
		"action": "list_node_signals",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": (
			str(target_node.name)
		),
		"node_type": (
			target_node.get_class()
		),
		"total_signals": signals.size(),
		"signals": signals,
	}

# ==========================================
# list_node_groups
# ==========================================
# Read-only group-membership inspection for a single
# node in the currently edited scene. The result comes
# from the node's real instance state (Node.get_groups()).
# No scene state is modified.


func list_node_groups_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"list_node_groups requires "
				+ "node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	if node_path.is_empty():

		return {
			"success": false,
			"error": (
				"list_node_groups requires a "
				+ "non-empty node_path (use \".\" "
				+ "for the edited scene root)."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	# Node.get_groups() is the authoritative Godot
	# source for instance group membership. It
	# returns StringName values; convert them to
	# plain strings and sort them so the result is
	# deterministic regardless of Godot's internal
	# group ordering.
	var groups: Array = []

	for group in target_node.get_groups():

		groups.append(str(group))

	groups.sort()

	return {
		"success": true,
		"action": "list_node_groups",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": (
			str(target_node.name)
		),
		"node_type": (
			target_node.get_class()
		),
		"total_groups": groups.size(),
		"groups": groups,
	}


# ==========================================
# get_node_children_summary
# ==========================================
# Lightweight child listing for one node: name, type,
# sibling index, and child count, without full subtree
# serialization. Preferred over get_scene_tree for large
# scenes when only immediate children are needed.


func get_node_children_summary_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("node_path"):

		return {
			"success": false,
			"error": (
				"get_node_children_summary requires "
				+ "node_path."
			)
		}

	var node_path: String = (
		str(data["node_path"]).strip_edges()
	)

	if node_path.is_empty():

		return {
			"success": false,
			"error": (
				"get_node_children_summary requires "
				+ "a non-empty node_path (use \".\" "
				+ "for the edited scene root)."
			)
		}

	var node_result := (
		scene_helpers
		.resolve_node_or_error(
			node_path
		)
	)

	if not node_result["success"]:
		return node_result

	var edited_scene_root: Node = (
		node_result["scene_root"]
	)

	var target_node: Node = (
		node_result["node"]
	)

	const MAX_CHILDREN_SUMMARY := 200

	var children: Array = []

	var omitted := 0

	var index := 0

	for child in target_node.get_children():

		if not (child is Node):
			continue

		if children.size() >= MAX_CHILDREN_SUMMARY:

			omitted += 1

			index += 1

			continue

		children.append(
			{
				"name": str(child.name),
				"node_type": child.get_class(),
				"index": index,
				"child_count": child.get_child_count(),
			}
		)

		index += 1

	return {
		"success": true,
		"action": "get_node_children_summary",
		"node_path": (
			scene_helpers
			.get_relative_node_path(
				edited_scene_root,
				target_node
			)
		),
		"node_name": str(target_node.name),
		"node_type": target_node.get_class(),
		"total_children": index,
		"truncated": omitted > 0,
		"omitted": omitted,
		"children": children,
	}

# ==========================================
# find_nodes_by_script
# ==========================================
# Read-only script-attachment inspection for the
# currently edited scene. Traverses the real scene
# tree and matches each node's live attached script
# (Node.get_script().resource_path) against the
# requested script path. No scene state is modified.


func find_nodes_by_script_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("script_path"):

		return {
			"success": false,
			"error": (
				"find_nodes_by_script requires "
				+ "script_path."
			)
		}

	var script_path: String = (
		str(data["script_path"]).strip_edges()
	)

	if script_path.is_empty():

		return {
			"success": false,
			"error": (
				"find_nodes_by_script requires a "
				+ "non-empty script_path."
			)
		}

	# Deterministic normalization: match against the
	# canonical Godot resource path. A request without
	# the res:// prefix is normalized by prepending it,
	# so "scripts/player.gd" and
	# "res://scripts/player.gd" are equivalent. No
	# fuzzy matching is performed.
	if not script_path.begins_with("res://"):

		script_path = (
			"res://"
			+ script_path
		)

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	var matching_nodes: Array = []

	# Reuses the exact find_nodes traversal and node
	# serialization via the shared collector; only the
	# script filter differs.
	collect_matching_nodes(
		edited_scene_root,
		edited_scene_root,
		matching_nodes,
		"",
		"",
		"exact",
		false,
		script_path
	)

	return {
		"success": true,
		"action": "find_nodes_by_script",
		"script_path": script_path,
		"count": matching_nodes.slice(
			0,
			FIND_NODES_MAX_RESULTS
		).size(),
		"total_matches": matching_nodes.size(),
		"truncated": (
			matching_nodes.size()
			> FIND_NODES_MAX_RESULTS
		),
		"limit": FIND_NODES_MAX_RESULTS,
		"nodes": matching_nodes.slice(
			0,
			FIND_NODES_MAX_RESULTS
		)
	}

# ==========================================
# find_nodes_by_group
# ==========================================
# Read-only group-membership inspection for the
# currently edited scene. Traverses the real scene
# tree and matches each node's live group membership
# (Node.is_in_group(), exact and case-sensitive)
# against the requested group name. No scene state
# is modified.


func find_nodes_by_group_from_request(
	data: Dictionary
) -> Dictionary:

	if not data.has("group_name"):

		return {
			"success": false,
			"error": (
				"find_nodes_by_group requires "
				+ "group_name."
			)
		}

	var group_name: String = (
		str(data["group_name"]).strip_edges()
	)

	if group_name.is_empty():

		return {
			"success": false,
			"error": (
				"find_nodes_by_group requires a "
				+ "non-empty group_name."
			)
		}

	var scene_result: Dictionary = (
		scene_helpers
		.get_edited_scene_root_or_error()
	)

	if not scene_result["success"]:
		return scene_result

	var edited_scene_root: Node = (
		scene_result["scene_root"]
	)

	var matching_nodes: Array = []

	# Reuses the exact find_nodes traversal and node
	# serialization via the shared collector; only the
	# group filter differs.
	collect_matching_nodes(
		edited_scene_root,
		edited_scene_root,
		matching_nodes,
		"",
		"",
		"exact",
		false,
		"",
		group_name
	)

	return {
		"success": true,
		"action": "find_nodes_by_group",
		"group_name": group_name,
		"count": matching_nodes.slice(
			0,
			FIND_NODES_MAX_RESULTS
		).size(),
		"total_matches": matching_nodes.size(),
		"truncated": (
			matching_nodes.size()
			> FIND_NODES_MAX_RESULTS
		),
		"limit": FIND_NODES_MAX_RESULTS,
		"nodes": matching_nodes.slice(
			0,
			FIND_NODES_MAX_RESULTS
		)
	}
# ==========================================
# get_project_settings
# ==========================================
# Read-only, bounded ProjectSettings inspection.
#
# Never dumps the whole database. Two mutually-combivable
# filters: exact `setting_names` and/or a bounded `prefix`.
# At least one must be provided. Prefix results are bounded by
# DEFAULT/MAX_SETTINGS_RESULT_LIMIT. Setting names matching a
# sensitive token are excluded (name only) to prevent accidental
# bulk exposure of credentials.. Values are serialized with the
# project's shared Variant serializer.


func get_project_settings_from_request(
	data: Dictionary
) -> Dictionary:

	var setting_names: Array = []
	var prefix := ""
	var limit := DEFAULT_SETTINGS_RESULT_LIMIT

	if (
		data.has("setting_names")
		and data["setting_names"] != null
	):
		if not data["setting_names"] is Array:
			return {
				"success": false,
				"error": (
					"get_project_settings setting_names must be a list."
				)
			}

		for raw_name in data["setting_names"]:

			var name := str(raw_name).strip_edges()

			if name.is_empty():
				continue

			if not setting_names.has(name):
				setting_names.append(name)

	if (
		data.has("prefix")
		and data["prefix"] != null
	):
		prefix = str(
			data["prefix"]
		).strip_edges()

	if (
		setting_names.is_empty()
		and prefix.is_empty()
	):

		return {
			"success": false,
			"error": (
				"get_project_settings requires at least one of "
				+ "non-empty setting_names or prefix."
			)
		}

	var use_limit := not prefix.is_empty()

	if use_limit and data.has("limit") and data["limit"] != null:

		var supplied_limit = data["limit"]

		if (
			typeof(supplied_limit) != TYPE_INT
			and typeof(supplied_limit) != TYPE_FLOAT
		):

			return _settings_limit_error()

		limit = int(supplied_limit)



		if (
			float(supplied_limit) != float(limit)
			or limit < 1
			or limit > MAX_SETTINGS_RESULT_LIMIT
		):

			return _settings_limit_error()

	var variant_serializer = VariantSerializerScript.new()

	var settings := {}
	var missing: Array = []
	var redacted: Array = []

	# 1. Exact requested names (always returned when present,
	# independent of the prefix limit). Missing names are reported
	# deterministically in `missing`;, they do not fail the request.
	for name in setting_names:

		if _is_sensitive_setting_name(name):
			redacted.append(name)

			continue

		if not ProjectSettings.has_setting(name):
			missing.append(name)
			continue

		settings[name] = (
			variant_serializer
			.serialize_property_value(
				ProjectSettings.get_setting(name)
			)
		)

	# 2. Prefix enumeration (bounded, lexicographically sorted)..
	var returned_prefix_matches := 0
	var total_prefix_matches := 0
	var truncated := false

	if not prefix.is_empty():

		var property_list: Array = (
			ProjectSettings.get_property_list()
		)

		var matching_keys: Array = []

		for entry in property_list:

			var key := str(
				entry.get(
					"name",
					""
				)
			)

			if not key.begins_with(prefix):
				continue

			if not settings.has(key):
				matching_keys.append(key)



		matching_keys.sort()

		total_prefix_matches = matching_keys.size()

		for key in matching_keys:

			if returned_prefix_matches >= limit:
				truncated = true
				break

			if _is_sensitive_setting_name(key):
				redacted.append(key)
				continue



			settings[key] = (
				variant_serializer
				.serialize_property_value(
					ProjectSettings.get_setting(key)
				)
			)

			returned_prefix_matches += 1

	var result := {
		"success": true,
		"action": "get_project_settings",
		"setting_names": setting_names,
		"prefix": prefix,
		"settings": settings,
		"missing": missing,
		"redacted": redacted
	}

	if not prefix.is_empty():
		result["total_matches"] = total_prefix_matches
		result["returned_matches"] = returned_prefix_matches
		result["truncated"] = truncated

	return result


func _is_sensitive_setting_name(
	setting_name: String
) -> bool:

	var lower_name := setting_name.to_lower()

	for token in SENSITIVE_SETTING_TOKENS:

		if lower_name.contains(token):
			return true

	return false


func _settings_limit_error() -> Dictionary:

	return {
		"success": false,
		"error": (
			"get_project_settings limit must be an "
			+ "integer from 1 to "
			+ str(MAX_SETTINGS_RESULT_LIMIT)
			+ "."
		)
	}

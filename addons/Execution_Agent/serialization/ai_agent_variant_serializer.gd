@tool
extends RefCounted

class_name AIAgentVariantSerializer

# ==========================================
# Variant serialization
# ==========================================


func serialize_property_value(
	value
):
	var value_type := (
		typeof(value)
	)

	match value_type:

		TYPE_NIL:
			return null

		TYPE_BOOL:
			return value

		TYPE_INT:
			return value

		TYPE_FLOAT:
			return value

		TYPE_STRING:
			return value

		TYPE_STRING_NAME:
			return str(value)

		TYPE_NODE_PATH:
			return {
				"type": "NodePath",
				"value": str(value)
			}

		TYPE_VECTOR2:
			return {
				"type": "Vector2",
				"x": value.x,
				"y": value.y
			}

		TYPE_VECTOR2I:
			return {
				"type": "Vector2i",
				"x": value.x,
				"y": value.y
			}

		TYPE_VECTOR3:
			return {
				"type": "Vector3",
				"x": value.x,
				"y": value.y,
				"z": value.z
			}

		TYPE_VECTOR3I:
			return {
				"type": "Vector3i",
				"x": value.x,
				"y": value.y,
				"z": value.z
			}

		TYPE_COLOR:
			return {
				"type": "Color",
				"r": value.r,
				"g": value.g,
				"b": value.b,
				"a": value.a
			}

		TYPE_RECT2:
			return {
				"type": "Rect2",
				"position": (
					serialize_property_value(
						value.position
					)
				),
				"size": (
					serialize_property_value(
						value.size
					)
				)
			}

		TYPE_RECT2I:
			return {
				"type": "Rect2i",
				"position": (
					serialize_property_value(
						value.position
					)
				),
				"size": (
					serialize_property_value(
						value.size
					)
				)
			}

		TYPE_TRANSFORM2D:
			return {
				"type": "Transform2D",
				"x": (
					serialize_property_value(
						value.x
					)
				),
				"y": (
					serialize_property_value(
						value.y
					)
				),
				"origin": (
					serialize_property_value(
						value.origin
					)
				)
			}

		TYPE_TRANSFORM3D:
			return {
				"type": "Transform3D",
				"basis": (
					serialize_property_value(
						value.basis
					)
				),
				"origin": (
					serialize_property_value(
						value.origin
					)
				)
			}

		TYPE_BASIS:
			return {
				"type": "Basis",
				"x": (
					serialize_property_value(
						value.x
					)
				),
				"y": (
					serialize_property_value(
						value.y
					)
				),
				"z": (
					serialize_property_value(
						value.z
					)
				)
			}

		TYPE_ARRAY:
			var serialized_array := []

			for item in value:
				serialized_array.append(
					serialize_property_value(
						item
					)
				)

			return serialized_array

		TYPE_DICTIONARY:
			var serialized_dictionary := {}

			for key in value:
				serialized_dictionary[
					str(key)
				] = (
					serialize_property_value(
						value[key]
					)
				)

			return serialized_dictionary

		TYPE_OBJECT:

			if value == null:
				return null

			if value is Node:
				return {
					"type": (
						value.get_class()
					),
					"object_type": "Node",
					"name": value.name,
					"display": (
						"<"
						+ value.get_class()
						+ ": "
						+ value.name
						+ ">"
					),
					"supported": false
				}

			return {
				"type": (
					value.get_class()
				),
				"object_type": "Object",
				"display": (
					"<"
					+ value.get_class()
					+ ">"
				),
				"supported": false
			}

	return {
		"type": (
			type_string(
				value_type
			)
		),
		"display": str(value),
		"supported": false
	}


# ==========================================
# Variant deserialization
# ==========================================


func deserialize_property_value(
	value,
	expected_type: int
) -> Dictionary:

	var result := {
		"success": true,
		"value": value
	}

	if value == null:

		if expected_type == TYPE_NIL:
			return result

		return {
			"success": true,
			"value": null
		}

	match expected_type:

		TYPE_BOOL:

			if typeof(value) != TYPE_BOOL:
				return _type_error(
					"bool",
					value
				)

			result["value"] = value
			return result

		TYPE_INT:

			if (
				typeof(value) != TYPE_INT
				and typeof(value) != TYPE_FLOAT
			):
				return _type_error(
					"int",
					value
				)

			result["value"] = int(value)
			return result

		TYPE_FLOAT:

			if (
				typeof(value) != TYPE_INT
				and typeof(value) != TYPE_FLOAT
			):
				return _type_error(
					"float",
					value
				)

			result["value"] = float(value)
			return result

		TYPE_STRING:

			if typeof(value) != TYPE_STRING:
				return _type_error(
					"String",
					value
				)

			result["value"] = value
			return result

		TYPE_STRING_NAME:

			if typeof(value) != TYPE_STRING:
				return _type_error(
					"StringName",
					value
				)

			result["value"] = StringName(
				value
			)

			return result

		TYPE_NODE_PATH:

			if typeof(value) == TYPE_STRING:

				result["value"] = NodePath(
					value
				)

				return result

			if (
				typeof(value) == TYPE_DICTIONARY
				and value.has("value")
			):

				result["value"] = NodePath(
					str(
						value["value"]
					)
				)

				return result

			return _type_error(
				"NodePath",
				value
			)

		TYPE_VECTOR2:

			return _deserialize_vector2(
				value
			)

		TYPE_VECTOR2I:

			return _deserialize_vector2i(
				value
			)

		TYPE_VECTOR3:

			return _deserialize_vector3(
				value
			)

		TYPE_VECTOR3I:

			return _deserialize_vector3i(
				value
			)

		TYPE_COLOR:

			return _deserialize_color(
				value
			)

		TYPE_ARRAY:

			if typeof(value) != TYPE_ARRAY:
				return _type_error(
					"Array",
					value
				)

			result["value"] = value
			return result

		TYPE_DICTIONARY:

			if typeof(value) != TYPE_DICTIONARY:
				return _type_error(
					"Dictionary",
					value
				)

			result["value"] = value
			return result

	return {
		"success": true,
		"value": value
	}


# ==========================================
# Vector helpers
# ==========================================


func _deserialize_vector2(
	value
) -> Dictionary:

	if (
		typeof(value) != TYPE_DICTIONARY
		or not value.has("x")
		or not value.has("y")
	):

		return _type_error(
			"Vector2",
			value
		)

	return {
		"success": true,
		"value": Vector2(
			float(value["x"]),
			float(value["y"])
		)
	}


func _deserialize_vector2i(
	value
) -> Dictionary:

	if (
		typeof(value) != TYPE_DICTIONARY
		or not value.has("x")
		or not value.has("y")
	):

		return _type_error(
			"Vector2i",
			value
		)

	return {
		"success": true,
		"value": Vector2i(
			int(value["x"]),
			int(value["y"])
		)
	}


func _deserialize_vector3(
	value
) -> Dictionary:

	if (
		typeof(value) != TYPE_DICTIONARY
		or not value.has("x")
		or not value.has("y")
		or not value.has("z")
	):

		return _type_error(
			"Vector3",
			value
		)

	return {
		"success": true,
		"value": Vector3(
			float(value["x"]),
			float(value["y"]),
			float(value["z"])
		)
	}


func _deserialize_vector3i(
	value
) -> Dictionary:

	if (
		typeof(value) != TYPE_DICTIONARY
		or not value.has("x")
		or not value.has("y")
		or not value.has("z")
	):

		return _type_error(
			"Vector3i",
			value
		)

	return {
		"success": true,
		"value": Vector3i(
			int(value["x"]),
			int(value["y"]),
			int(value["z"])
		)
	}


# ==========================================
# Color helper
# ==========================================


func _deserialize_color(
	value
) -> Dictionary:

	if (
		typeof(value) != TYPE_DICTIONARY
		or not value.has("r")
		or not value.has("g")
		or not value.has("b")
	):

		return _type_error(
			"Color",
			value
		)

	var alpha := 1.0

	if value.has("a"):
		alpha = float(
			value["a"]
		)

	return {
		"success": true,
		"value": Color(
			float(value["r"]),
			float(value["g"]),
			float(value["b"]),
			alpha
		)
	}


# ==========================================
# Error helper
# ==========================================


func _type_error(
	expected_type_name: String,
	value
) -> Dictionary:

	return {
		"success": false,
		"error": (
			"Expected "
			+ expected_type_name
			+ " value but received "
			+ type_string(
				typeof(value)
			)
			+ "."
		)
	}
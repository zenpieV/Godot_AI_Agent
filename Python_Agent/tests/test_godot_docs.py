"""
Tests for the Python-side documentation tools (tools/godot_docs.py).

Guarantees:
- the bundled version-pinned reference loads and reports its version,
- get_class_documentation returns bounded, structured sections and
  structured failures for unknown classes/sections,
- search_documentation is ranked, bounded, and validates inputs,
- nothing is fabricated for classes without a given section.
"""

import pytest

from tools import godot_docs


def test_bundle_loads_and_reports_version():
    version = godot_docs.get_docs_version()
    assert version == "4.7.2"


def test_get_class_documentation_core_class():
    result = godot_docs.get_class_documentation("Node")
    assert result["success"] is True
    assert result["class_name"] == "Node"
    assert result["docs_version"] == "4.7.2"
    assert result["inherits"] == "Object"
    assert "Base class" in result["brief"]
    assert "get_node" in result["methods"]
    assert "tree_entered" in result["signals"]
    assert result["methods"]["get_node"]["signature"].startswith(
        "get_node("
    )


def test_get_class_documentation_sections_filter():
    result = godot_docs.get_class_documentation(
        "Node", sections=["brief", "signals"]
    )
    assert result["success"] is True
    assert "signals" in result
    # Unrequested sections are absent, not fabricated as empty.
    assert "methods" not in result
    assert "description" not in result


def test_get_class_documentation_unknown_class():
    result = godot_docs.get_class_documentation("NotARealClass")
    assert result["success"] is False
    assert "class not found" in result["error"]
    assert "search_documentation" in result["error"]


def test_get_class_documentation_unknown_section():
    result = godot_docs.get_class_documentation(
        "Node", sections=["nope"]
    )
    assert result["success"] is False
    assert "unknown section" in result["error"]
    assert "Valid sections" in result["error"]


def test_get_class_documentation_invalid_inputs():
    assert godot_docs.get_class_documentation("")["success"] is False
    assert (
        godot_docs.get_class_documentation("Node", sections="brief")[
            "success"
        ]
        is False
    )


def test_search_documentation_exact_class_match_ranks_first():
    result = godot_docs.search_documentation("Timer", limit=5)
    assert result["success"] is True
    assert result["docs_version"] == "4.7.2"
    assert result["total_matches"] >= 1
    first = result["matches"][0]
    assert first["kind"] == "class"
    assert first["class_name"] == "Timer"


def test_search_documentation_member_match():
    result = godot_docs.search_documentation("tree_entered", limit=5)
    assert result["success"] is True
    kinds = {(m["kind"], m["class_name"]) for m in result["matches"]}
    assert ("signal", "Node") in kinds


def test_search_documentation_bounded_and_truncated_flag():
    result = godot_docs.search_documentation("node", limit=3)
    assert result["success"] is True
    assert len(result["matches"]) <= 3
    assert result["limit"] == 3
    # "node" matches many classes: the result must report truncation.
    if result["total_matches"] > 3:
        assert result["truncated"] is True


def test_search_documentation_invalid_inputs():
    assert godot_docs.search_documentation("")["success"] is False
    assert godot_docs.search_documentation("x", limit=0)["success"] is False
    assert godot_docs.search_documentation("x", limit=26)["success"] is False
    assert godot_docs.search_documentation("x", limit="5")["success"] is False


def test_search_documentation_short_query_skips_fulltext():
    """Full-text matching requires 4+ chars; short queries only match
    names, keeping results precise and bounded."""
    result = godot_docs.search_documentation("abc", limit=25)
    assert result["success"] is True
    for match in result["matches"]:
        assert match["kind"] in ("class", "method", "property", "signal")

"""
Godot class-reference documentation access for the agent.

Serves the two Python-side documentation tools:

- get_class_documentation(class_name, sections=None)
- search_documentation(query, limit=None)

The data source is the bundled, version-pinned class reference
produced by scripts/prepare_godot_docs.py from the official
engine docs XML. The bundle's version field is surfaced in every
result so callers always know which engine version the docs
describe (see docs/MODEL_KNOWLEDGE_DRIFT.md for why version
matching matters).

These tools are the project's first that never touch the Godot
bridge: the registry handlers read this module directly. Results
are structured and bounded like every other tool result; nothing
is ever fabricated - unknown classes produce structured failures.
"""

import gzip
import json
from pathlib import Path

# Search and result bounds (mirroring the bridge tool conventions).

DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 25
SNIPPET_RADIUS = 100
MAX_SNIPPET_LENGTH = 2 * SNIPPET_RADIUS + 1

ALL_SECTIONS = (
    "brief",
    "description",
    "methods",
    "constructors",
    "properties",
    "signals",
    "constants",
    "theme_items",
)

_bundle = None


def _load_bundle():
    """Load the gzip JSON bundle once, lazily."""

    global _bundle

    if _bundle is not None:
        return _bundle

    data_dir = Path(__file__).resolve().parent.parent / "data"

    bundles = sorted(data_dir.glob("godot_docs_*.json.gz"))

    if not bundles:
        raise FileNotFoundError(
            "No godot_docs_*.json.gz bundle found in "
            + str(data_dir)
            + ". Run scripts/prepare_godot_docs.py first."
        )

    # Lexicographic order == newest version last in practice;
    # prefer the most recent bundle available.
    bundle_path = bundles[-1]

    with gzip.open(bundle_path, "rt", encoding="utf-8") as handle:
        _bundle = json.load(handle)

    return _bundle


def get_docs_version():
    """Engine version the bundled docs describe."""

    return _load_bundle().get("version", "unknown")


def get_class_documentation(
    class_name,
    sections=None,
):
    """
    Return the structured documentation entry for one Godot
    class from the bundled reference.

    sections optionally restricts the response to a subset of:
    brief, description, methods, constructors, properties,
    signals, constants, theme_items. Unknown sections are
    rejected; a known class with requested-but-empty sections
    reports them as empty, never fabricated.
    """

    bundle = _load_bundle()

    if not isinstance(class_name, str) or not class_name.strip():
        return {
            "success": False,
            "error": (
                "get_class_documentation requires a "
                "non-empty class_name."
            ),
        }

    class_name = class_name.strip()

    requested_sections = ALL_SECTIONS

    if sections is not None:
        if not isinstance(sections, list) or not all(
            isinstance(section, str) for section in sections
        ):
            return {
                "success": False,
                "error": (
                    "get_class_documentation sections must "
                    "be a list of strings."
                ),
            }

        unknown = [
            section
            for section in sections
            if section not in ALL_SECTIONS
        ]

        if unknown:
            return {
                "success": False,
                "error": (
                    "get_class_documentation received "
                    "unknown section(s): "
                    + ", ".join(unknown)
                    + ". Valid sections: "
                    + ", ".join(ALL_SECTIONS)
                ),
            }

        # Preserve bundle order, drop duplicates.
        requested_sections = tuple(
            section
            for section in ALL_SECTIONS
            if section in sections
        )

    entry = bundle["classes"].get(class_name)

    if entry is None:
        return {
            "success": False,
            "error": (
                "get_class_documentation: class not found in "
                "the bundled reference: "
                + class_name
                + ". Use search_documentation to discover "
                "valid class names."
            ),
        }

    result = {
        "success": True,
        "action": "get_class_documentation",
        "class_name": class_name,
        "docs_version": bundle.get("version", "unknown"),
    }

    for section in requested_sections:
        result[section] = entry.get(section, {})

    # Inherits is always included: it is tiny and anchors the
    # class hierarchy.
    result["inherits"] = entry.get("inherits", "")

    return result


def _make_snippet(text, position):
    """Bounded snippet around a match position."""

    start = max(0, position - SNIPPET_RADIUS)
    end = min(len(text), position + SNIPPET_RADIUS)

    snippet = text[start:end].replace("\n", " ").strip()

    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    if len(snippet) > MAX_SNIPPET_LENGTH + 6:
        snippet = snippet[: MAX_SNIPPET_LENGTH + 6]

    return snippet


def search_documentation(
    query,
    limit=None,
):
    """
    Bounded case-insensitive search across class names, member
    names, and documentation text of the bundled reference.

    Ranking: exact class name > class name substring > member
    name match > description match. Every match carries a
    bounded snippet; total_matches and truncated report whether
    the result is exhaustive.
    """

    bundle = _load_bundle()

    if not isinstance(query, str) or not query.strip():
        return {
            "success": False,
            "error": (
                "search_documentation requires a non-empty "
                "query."
            ),
        }

    effective_limit = DEFAULT_SEARCH_LIMIT

    if limit is not None:
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > MAX_SEARCH_LIMIT
        ):
            return {
                "success": False,
                "error": (
                    "search_documentation limit must be an "
                    "integer between 1 and "
                    + str(MAX_SEARCH_LIMIT)
                    + "."
                ),
            }

        effective_limit = limit

    needle = query.strip().lower()

    matches = []

    for class_name, entry in bundle["classes"].items():
        class_lower = class_name.lower()

        if class_lower == needle:
            matches.append(
                {
                    "kind": "class",
                    "class_name": class_name,
                    "member_name": "",
                    "rank": 0,
                    "snippet": entry.get("brief", ""),
                }
            )
        elif needle in class_lower:
            matches.append(
                {
                    "kind": "class",
                    "class_name": class_name,
                    "member_name": "",
                    "rank": 1,
                    "snippet": entry.get("brief", ""),
                }
            )

        for method_name, method_info in entry.get(
            "methods", {}
        ).items():
            if needle in method_name.lower():
                matches.append(
                    {
                        "kind": "method",
                        "class_name": class_name,
                        "member_name": method_name,
                        "rank": 2,
                        "snippet": method_info.get(
                            "signature", ""
                        ),
                    }
                )

        for member_name, member_info in entry.get(
            "properties", {}
        ).items():
            if needle in member_name.lower():
                matches.append(
                    {
                        "kind": "property",
                        "class_name": class_name,
                        "member_name": member_name,
                        "rank": 2,
                        "snippet": (
                            member_info.get("type", "")
                            + " — "
                            + member_info.get(
                                "description", ""
                            )
                        ),
                    }
                )

        for signal_name, signal_info in entry.get(
            "signals", {}
        ).items():
            if needle in signal_name.lower():
                matches.append(
                    {
                        "kind": "signal",
                        "class_name": class_name,
                        "member_name": signal_name,
                        "rank": 2,
                        "snippet": signal_info.get(
                            "signature", ""
                        ),
                    }
                )

        # Full-text description matches only when the query is
        # long enough to be meaningful, and only one snippet per
        # class to keep the result bounded.
        if len(needle) >= 4:
            haystack = (
                entry.get("description", "")
                or entry.get("brief", "")
            )
            position = haystack.lower().find(needle)
            if position != -1:
                matches.append(
                    {
                        "kind": "description",
                        "class_name": class_name,
                        "member_name": "",
                        "rank": 3,
                        "snippet": _make_snippet(
                            haystack, position
                        ),
                    }
                )

    matches.sort(
        key=lambda match: (
            match["rank"],
            match["class_name"].lower(),
            match["member_name"].lower(),
        )
    )

    total_matches = len(matches)
    truncated = total_matches > effective_limit

    return {
        "success": True,
        "action": "search_documentation",
        "query": query.strip(),
        "docs_version": bundle.get("version", "unknown"),
        "total_matches": total_matches,
        "truncated": truncated,
        "limit": effective_limit,
        "matches": matches[:effective_limit],
    }

"""
Convert Godot engine class-reference XML into the compact gzip JSON
bundle consumed by tools/godot_docs.py.

Usage:

    python scripts/prepare_godot_docs.py <path-to-doc/classes-dir> <version>

Example:

    git clone --depth 1 --branch 4.7.2-stable --filter=blob:none \
        --sparse https://github.com/godotengine/godot.git /tmp/godot_src
    cd /tmp/godot_src && git sparse-checkout set doc/classes
    python scripts/prepare_godot_docs.py /tmp/godot_src/doc/classes 4.7.2

The output is written to data/godot_docs_<version>.json.gz next to
this script's project root. The version string is embedded in the
bundle and surfaced by the documentation tools so callers can see
which engine version the docs describe.

Godot BBCode markup is stripped: paired tags ([b], [code],
[codeblock], ...) are removed and their inner text kept;
[br] becomes a newline; cross-references such as
[method get_node] keep the referenced name.
"""

import gzip
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree


BB_CODE_NEWLINE = re.compile(r"\[(?:br|p)(?:\s*/)?\]")
BB_CODE_TAG = re.compile(r"\[/?(?:b|i|u|s|code|codeblock|center|url|img|td|tr|table|col|lb|rb)(?:\s[^\]]*)?\]")


def clean_text(text):
    """Strip Godot BBCode, keep content, normalize whitespace."""

    if text is None:
        return ""

    text = BB_CODE_NEWLINE.sub("\n", text)
    text = BB_CODE_TAG.sub("", text)
    text = text.replace("\r\n", "\n")

    # Collapse runs of blank lines left behind by removed blocks.
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    return text.strip()


def parse_class(xml_path: Path):
    root = ElementTree.parse(xml_path).getroot()

    if root.tag != "class":
        return None

    info = {
        "inherits": root.attrib.get("inherits", ""),
        "brief": "",
        "description": "",
        "methods": {},
        "constructors": {},
        "properties": {},
        "signals": {},
        "constants": {},
        "theme_items": {},
    }

    brief = root.find("brief_description")
    if brief is not None and brief.text:
        info["brief"] = clean_text(brief.text)

    description = root.find("description")
    if description is not None and description.text:
        info["description"] = clean_text(description.text)

    for method in root.iter("method"):
        name = method.attrib.get("name", "")
        if not name:
            continue

        return_element = method.find("return")
        return_type = (
            return_element.attrib.get("type", "void")
            if return_element is not None
            else "void"
        )

        args = []
        for param in method.iter("param"):
            args.append(
                "{type} {name}".format(
                    type=param.attrib.get("type", ""),
                    name=param.attrib.get("name", ""),
                ).strip()
            )

        info["methods"][name] = {
            "signature": "{name}({args}) -> {return_type}".format(
                name=name,
                args=", ".join(args),
                return_type=return_type,
            ),
            "description": clean_text(method.findtext("description")),
        }

    for constructor in root.iter("constructor"):
        name = constructor.attrib.get("name", "")
        if not name:
            continue
        info["constructors"][name] = {
            "description": clean_text(
                constructor.findtext("description")
            ),
        }

    for member in root.iter("member"):
        name = member.attrib.get("name", "")
        if not name:
            continue
        info["properties"][name] = {
            "type": member.attrib.get("type", ""),
            "default": member.attrib.get("default", ""),
            "description": clean_text(
                member.text or ""
            ),
        }

    for signal in root.iter("signal"):
        name = signal.attrib.get("name", "")
        if not name:
            continue
        args = [
            "{type} {name}".format(
                type=param.attrib.get("type", ""),
                name=param.attrib.get("name", ""),
            ).strip()
            for param in signal.iter("param")
        ]
        info["signals"][name] = {
            "signature": "{name}({args})".format(
                name=name, args=", ".join(args)
            ),
            "description": clean_text(
                signal.findtext("description")
            ),
        }

    for constant in root.iter("constant"):
        name = constant.attrib.get("name", "")
        if not name:
            continue
        entry = {
            "value": constant.attrib.get("value", ""),
            "description": clean_text(
                constant.text or ""
            ),
        }
        enum_name = constant.attrib.get("enum", "")
        if enum_name:
            entry["enum"] = enum_name
        info["constants"][name] = entry

    for theme_item in root.iter("theme_item"):
        name = theme_item.attrib.get("name", "")
        if not name:
            continue
        info["theme_items"][name] = {
            "type": theme_item.attrib.get("type", ""),
            "description": clean_text(
                theme_item.text or ""
            ),
        }

    # Drop empty sections so the bundle stays compact.
    return {
        name: value
        for name, value in info.items()
        if value
    }


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    classes_dir = Path(sys.argv[1])
    version = sys.argv[2]

    xml_files = sorted(classes_dir.glob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {classes_dir}")
        sys.exit(1)

    classes = {}
    for xml_path in xml_files:
        parsed = parse_class(xml_path)
        if parsed is not None:
            classes[xml_path.stem] = parsed

    bundle = {
        "version": version,
        "class_count": len(classes),
        "classes": classes,
    }

    output_path = (
        Path(__file__).resolve().parent.parent
        / "data"
        / f"godot_docs_{version}.json.gz"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    raw = json.dumps(bundle, ensure_ascii=False).encode("utf-8")

    with gzip.open(output_path, "wb", compresslevel=9) as handle:
        handle.write(raw)

    print(
        f"Wrote {output_path} "
        f"({output_path.stat().st_size / 1024:.0f} KiB compressed, "
        f"{len(raw) / 1024 / 1024:.1f} MiB raw, "
        f"{len(classes)} classes)"
    )


if __name__ == "__main__":
    main()

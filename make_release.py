"""Build the distributable plugin release zip.

The zip contains exactly the two folders a Godot project needs to
run the agent:

    addons/Execution_Agent/   (the EditorPlugin: bridge, tools, panel)
    Python_Agent/             (the agent: providers, tools, docs bundle)

Secrets and machine-local files are excluded by construction:
.env, logs, agent.log, __pycache__/.pytest_cache caches, and the
personal clipboard scratchpad. Run from the repository root:

    py make_release.py

The output file is named Godot_AI_Agent-plugin-<version>.zip with
the version taken from addons/Execution_Agent/plugin.cfg.
"""

import os
import re
import zipfile


REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

ZIP_ROOTS = (
    os.path.join("addons", "Execution_Agent"),
    "Python_Agent",
)

# Any directory with one of these names is skipped entirely.
# Virtual environments are machine-specific (Windows .pyd
# binaries) and duplicate what requirements.txt installs.
EXCLUDED_DIRECTORIES = {
    "__pycache__",
    ".pytest_cache",
    "logs",
    ".venv",
    "venv",
    "env",
}

# Any file whose name matches one of these patterns is skipped.
EXCLUDED_FILE_PATTERNS = (
    ".env",
    ".env.*",
    "agent.log",
    "clipboard.md",
)


def is_excluded(relative_path, file_name):
    if file_name == "clipboard.md" and relative_path.replace(
        os.sep, "/"
    ).startswith("Python_Agent/docs/"):
        return True

    for pattern in EXCLUDED_FILE_PATTERNS:
        if re.fullmatch(
            pattern.replace(".", r"\.").replace("*", ".*"),
            file_name,
        ):
            return True

    return False


def read_plugin_version():
    plugin_cfg = os.path.join(
        REPO_ROOT,
        "addons",
        "Execution_Agent",
        "plugin.cfg",
    )

    with open(plugin_cfg, encoding="utf-8") as handle:
        match = re.search(
            r"^version\s*=\s*\"([^\"]+)\"",
            handle.read(),
            re.MULTILINE,
        )

    return match.group(1) if match else "0.0"


def build_release_zip():
    version = read_plugin_version()

    output_name = (
        f"Godot_AI_Agent-plugin-{version}.zip"
    )

    output_path = os.path.join(REPO_ROOT, output_name)

    included = 0

    with zipfile.ZipFile(
        output_path,
        "w",
        zipfile.ZIP_DEFLATED,
    ) as archive:

        for zip_root in ZIP_ROOTS:

            absolute_root = os.path.join(REPO_ROOT, zip_root)

            for directory, dir_names, file_names in os.walk(
                absolute_root
            ):

                dir_names[:] = [
                    d
                    for d in dir_names
                    if d not in EXCLUDED_DIRECTORIES
                ]

                for file_name in file_names:

                    absolute_file = os.path.join(
                        directory,
                        file_name,
                    )

                    relative_file = os.path.relpath(
                        absolute_file,
                        REPO_ROOT,
                    )

                    if is_excluded(
                        relative_file,
                        file_name,
                    ):
                        continue

                    archive.write(
                        absolute_file,
                        relative_file,
                    )

                    included += 1

    # Hard guarantee: the release must never carry secrets.
    with zipfile.ZipFile(output_path) as archive:
        for entry in archive.namelist():
            assert not entry.replace(os.sep, "/").endswith(
                "/.env"
            ), "release zip contains .env"

    size_kb = os.path.getsize(output_path) // 1024

    print(f"Built {output_name}: {included} files, ~{size_kb} KB")
    print("Attach it to a GitHub Release (see README).")


if __name__ == "__main__":
    build_release_zip()

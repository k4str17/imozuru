#!/usr/bin/env python3
"""Validate that plugin distribution metadata and its version stay in sync."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_NAME = "imozuru"
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
PLUGIN_RESOURCES = (
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
)


def fail(message: str) -> None:
    raise SystemExit(f"ERROR: {message}")


def run_git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return completed.stdout


def load_json_file(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"{relative_path}: invalid or unreadable JSON: {exc}")
    if not isinstance(data, dict):
        fail(f"{relative_path}: top level must be a JSON object")
    return data


def load_json_at_ref(ref: str, relative_path: str) -> dict[str, Any]:
    try:
        raw = run_git("show", f"{ref}:{relative_path}")
        data = json.loads(raw)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        fail(f"{relative_path}: could not read valid JSON at {ref}: {exc}")
    if not isinstance(data, dict):
        fail(f"{relative_path}@{ref}: top level must be a JSON object")
    return data


def parse_semver(version: object, location: str) -> tuple[int, int, int]:
    if not isinstance(version, str):
        fail(f"{location}: version must be a string")
    match = SEMVER.fullmatch(version)
    if not match:
        fail(
            f"{location}: version must be stable SemVer MAJOR.MINOR.PATCH, "
            f"got {version!r}"
        )
    return tuple(map(int, match.groups()))


def find_plugin(marketplace: dict[str, Any], location: str) -> dict[str, Any]:
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        fail(f"{location}: plugins must be an array")

    matches = [
        item
        for item in plugins
        if isinstance(item, dict) and item.get("name") == PLUGIN_NAME
    ]
    if len(matches) != 1:
        fail(
            f"{location}: expected exactly one {PLUGIN_NAME!r} plugin entry, "
            f"found {len(matches)}"
        )
    return matches[0]


def validate_current_metadata(version: str) -> None:
    claude_plugin = load_json_file(".claude-plugin/plugin.json")
    if claude_plugin.get("version") != version:
        fail(
            ".claude-plugin/plugin.json: version must match plugin.json "
            f"({version}), got {claude_plugin.get('version')!r}"
        )

    claude_marketplace = load_json_file(".claude-plugin/marketplace.json")
    claude_entry = find_plugin(
        claude_marketplace, ".claude-plugin/marketplace.json"
    )
    if claude_entry.get("version") != version:
        fail(
            ".claude-plugin/marketplace.json: imozuru version must match "
            f"plugin.json ({version}), got {claude_entry.get('version')!r}"
        )

    codex_marketplace = load_json_file(".agents/plugins/marketplace.json")
    codex_entry = find_plugin(
        codex_marketplace, ".agents/plugins/marketplace.json"
    )
    source = codex_entry.get("source")
    expected_ref = f"v{version}"
    if not isinstance(source, dict):
        fail(".agents/plugins/marketplace.json: imozuru source must be an object")
    if source.get("ref") != expected_ref:
        fail(
            ".agents/plugins/marketplace.json: imozuru source.ref must match "
            f"plugin.json ({expected_ref}), got {source.get('ref')!r}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        required=True,
        help="Base commit SHA used to determine changed plugin resources.",
    )
    args = parser.parse_args()

    changed = {
        line.strip()
        for line in run_git(
            "diff", "--name-only", args.base, "HEAD", "--", *PLUGIN_RESOURCES
        ).splitlines()
        if line.strip()
    }

    current_manifest = load_json_file("plugin.json")
    current_version = current_manifest.get("version")
    current_tuple = parse_semver(current_version, "plugin.json")
    assert isinstance(current_version, str)

    validate_current_metadata(current_version)

    if not changed:
        print(
            "Plugin distribution metadata is internally consistent; "
            "no guarded resources changed."
        )
        return

    base_manifest = load_json_at_ref(args.base, "plugin.json")
    base_version = base_manifest.get("version")
    base_tuple = parse_semver(base_version, f"plugin.json@{args.base}")
    assert isinstance(base_version, str)

    if current_version == base_version:
        fail(
            "plugin distribution resources changed without updating "
            f"plugin.json.version ({current_version}). Changed: "
            + ", ".join(sorted(changed))
        )

    if current_tuple <= base_tuple:
        fail(
            "plugin.json.version must increase when plugin distribution resources "
            f"change: base={base_version}, current={current_version}"
        )

    print(
        "Plugin version policy satisfied: "
        f"{base_version} -> {current_version}; changed: "
        + ", ".join(sorted(changed))
    )


if __name__ == "__main__":
    main()

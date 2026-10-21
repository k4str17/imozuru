#!/usr/bin/env python3
"""Synchronize plugin release metadata and optionally bump the plugin version."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$")
PLUGIN_NAME = "imozuru"


def load_json(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise SystemExit(f"{relative_path}: top level must be a JSON object")
    return data


def write_json(relative_path: str, data: dict[str, Any]) -> None:
    path = ROOT / relative_path
    with path.open("w", encoding="utf-8", newline="\\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\\n")


def bump_version(version: str, bump: str) -> str:
    match = SEMVER.fullmatch(version)
    if not match:
        raise SystemExit(
            f"plugin.json version must be stable SemVer (MAJOR.MINOR.PATCH): {version!r}"
        )

    major, minor, patch = map(int, match.groups())
    if bump == "none":
        return version
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise SystemExit(f"unsupported bump: {bump}")


def with_version_after_name(data: dict[str, Any], version: str) -> dict[str, Any]:
    if "name" not in data:
        raise SystemExit("manifest entry is missing name")

    updated: dict[str, Any] = {}
    for key, value in data.items():
        if key == "version":
            continue
        updated[key] = value
        if key == "name":
            updated["version"] = version
    return updated


def find_plugin(marketplace: dict[str, Any], relative_path: str) -> tuple[list[Any], int]:
    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list):
        raise SystemExit(f"{relative_path}: plugins must be an array")

    matches = [
        index
        for index, item in enumerate(plugins)
        if isinstance(item, dict) and item.get("name") == PLUGIN_NAME
    ]
    if len(matches) != 1:
        raise SystemExit(
            f"{relative_path}: expected exactly one {PLUGIN_NAME!r} plugin entry, found {len(matches)}"
        )
    return plugins, matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--bump",
        choices=("none", "patch", "minor", "major"),
        required=True,
        help="Version bump to apply before synchronizing release metadata.",
    )
    args = parser.parse_args()

    portable = load_json("plugin.json")
    current = portable.get("version")
    if not isinstance(current, str):
        raise SystemExit("plugin.json: version must be a string")

    version = bump_version(current, args.bump)
    portable["version"] = version

    claude_plugin = load_json(".claude-plugin/plugin.json")
    claude_plugin = with_version_after_name(claude_plugin, version)

    claude_marketplace = load_json(".claude-plugin/marketplace.json")
    claude_plugins, claude_index = find_plugin(
        claude_marketplace, ".claude-plugin/marketplace.json"
    )
    claude_plugins[claude_index] = with_version_after_name(
        claude_plugins[claude_index], version
    )

    codex_marketplace = load_json(".agents/plugins/marketplace.json")
    codex_plugins, codex_index = find_plugin(
        codex_marketplace, ".agents/plugins/marketplace.json"
    )
    codex_entry = codex_plugins[codex_index]
    source = codex_entry.get("source")
    if not isinstance(source, dict) or source.get("source") != "url":
        raise SystemExit(
            ".agents/plugins/marketplace.json: imozuru must use a URL source"
        )
    source["ref"] = f"v{version}"

    write_json("plugin.json", portable)
    write_json(".claude-plugin/plugin.json", claude_plugin)
    write_json(".claude-plugin/marketplace.json", claude_marketplace)
    write_json(".agents/plugins/marketplace.json", codex_marketplace)

    print(version)


if __name__ == "__main__":
    main()

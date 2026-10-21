#!/usr/bin/env python3
"""Validate plugin version policy for release-bearing resources."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
GUARDED_PATHS = (
    "plugin.json",
    ".claude-plugin/plugin.json",
    "skills/",
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        required=True,
        help="Base commit SHA used to determine release-bearing changes.",
    )
    args = parser.parse_args()

    changed = {
        line.strip()
        for line in run_git(
            "diff", "--name-only", args.base, "HEAD", "--", *GUARDED_PATHS
        ).splitlines()
        if line.strip()
    }

    current_manifest = load_json_file("plugin.json")
    current_version = current_manifest.get("version")
    current_tuple = parse_semver(current_version, "plugin.json")
    assert isinstance(current_version, str)

    claude_manifest = load_json_file(".claude-plugin/plugin.json")
    if claude_manifest.get("version") != current_version:
        fail(
            ".claude-plugin/plugin.json: version must match plugin.json "
            f"({current_version}), got {claude_manifest.get('version')!r}"
        )

    if not changed:
        print(
            "Plugin manifests are internally consistent; "
            "no release-bearing resources changed."
        )
        return

    base_manifest = load_json_at_ref(args.base, "plugin.json")
    base_version = base_manifest.get("version")
    base_tuple = parse_semver(base_version, f"plugin.json@{args.base}")
    assert isinstance(base_version, str)

    if current_version == base_version:
        fail(
            "release-bearing plugin resources changed without updating "
            f"plugin.json.version ({current_version}). Changed: "
            + ", ".join(sorted(changed))
        )

    if current_tuple <= base_tuple:
        fail(
            "plugin.json.version must increase when release-bearing resources "
            f"change: base={base_version}, current={current_version}"
        )

    print(
        "Plugin version policy satisfied: "
        f"{base_version} -> {current_version}; changed: "
        + ", ".join(sorted(changed))
    )


if __name__ == "__main__":
    main()

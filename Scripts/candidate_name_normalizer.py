#!/usr/bin/env python3
"""Normalize candidate display fields across JSON data files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_pa_data_layers as layers  # noqa: E402


def normalize_node(node) -> int:
    changes = 0
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str) and (key.endswith("_candidate") or key in {"candidate", "demCandidate", "repCandidate"}):
                normalized = layers.normalize_candidate_label(value)
                if normalized != value:
                    node[key] = normalized
                    changes += 1
            else:
                changes += normalize_node(value)
    elif isinstance(node, list):
        for value in node:
            changes += normalize_node(value)
    return changes


def json_paths(target: Path):
    if target.is_file() and target.suffix.lower() == ".json":
        yield target
    elif target.is_dir():
        for path in sorted(target.rglob("*.json")):
            if ".pre-" not in path.name.lower() and "backup" not in path.name.lower():
                yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("targets", nargs="+", type=Path)
    args = parser.parse_args()
    changed_files = []
    changed_values = 0
    for target in args.targets:
        for path in json_paths(target):
            payload = json.loads(path.read_text(encoding="utf-8"))
            count = normalize_node(payload)
            if not count:
                continue
            changed_files.append(str(path))
            changed_values += count
            if not args.check:
                path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print({"changed_files": len(changed_files), "changed_values": changed_values})
    if args.check and changed_files:
        for path in changed_files[:50]:
            print(path)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

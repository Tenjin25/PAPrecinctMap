#!/usr/bin/env python3
"""Restore candidate display labels from an earlier district JSON revision."""

import argparse
import io
import json
import subprocess
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISTRICT_DIR = ROOT / "data" / "district_contests"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ref", required=True)
    args = parser.parse_args()

    archive = subprocess.run(
        ["git", "archive", "--format=tar", args.source_ref, "data/district_contests"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    ).stdout

    restored_rows = 0
    changed_files = 0
    missing_rows = []
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as old_tree:
        members = {member.name: member for member in old_tree.getmembers() if member.isfile()}
        for path in sorted(DISTRICT_DIR.glob("*.json")):
            if path.name == "manifest.json":
                continue
            member_name = f"data/district_contests/{path.name}"
            member = members.get(member_name)
            if member is None:
                continue
            old_handle = old_tree.extractfile(member)
            if old_handle is None:
                continue
            old = json.load(old_handle)
            current = json.loads(path.read_text(encoding="utf-8"))
            old_results = old.get("general", {}).get("results", {})
            current_results = current.get("general", {}).get("results", {})
            file_changed = False
            for district, row in current_results.items():
                old_row = old_results.get(district)
                if old_row is None:
                    missing_rows.append(f"{path.name}:{district}")
                    continue
                for field in ("dem_candidate", "rep_candidate"):
                    old_value = old_row.get(field, "")
                    if row.get(field, "") != old_value:
                        row[field] = old_value
                        file_changed = True
                restored_rows += 1
            if file_changed:
                path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
                changed_files += 1

    print(json.dumps({
        "source_ref": args.source_ref,
        "changed_files": changed_files,
        "restored_rows": restored_rows,
        "missing_rows": missing_rows,
    }, indent=2))
    return 1 if missing_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())

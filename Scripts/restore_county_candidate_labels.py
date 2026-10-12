#!/usr/bin/env python3
"""Restore reviewed county candidate labels without changing vote totals."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTESTS = ROOT / "data" / "contests"
AGGREGATE = ROOT / "data" / "pa_elections_aggregated.json"
CANDIDATE_FIELDS = ("dem_candidate", "rep_candidate")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload):
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def load_from_ref(ref: str, relative_path: str):
    result = subprocess.run(
        ["git", "show", f"{ref}:{relative_path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-ref", default="6bfdd8b")
    args = parser.parse_args()

    aggregate = load(AGGREGATE)
    changed_files = 0
    changed_rows = 0
    vote_changes = 0

    for path in sorted(CONTESTS.glob("*.json")):
        if path.name == "manifest.json":
            continue
        relative = path.relative_to(ROOT).as_posix()
        try:
            previous = load_from_ref(args.source_ref, relative)
        except (subprocess.CalledProcessError, json.JSONDecodeError):
            continue

        current = load(path)
        old_rows = {
            str(row.get("county") or "").upper(): row
            for row in previous.get("rows", [])
        }
        before_votes = [
            tuple(row.get(field) for field in ("county", "dem_votes", "rep_votes", "other_votes", "total_votes"))
            for row in current.get("rows", [])
        ]
        file_changed = False
        for row in current.get("rows", []):
            old = old_rows.get(str(row.get("county") or "").upper())
            if not old:
                continue
            row_changed = False
            for field in CANDIDATE_FIELDS:
                label = str(old.get(field) or "").strip()
                if label and row.get(field) != label:
                    row[field] = label
                    row_changed = True
            if row_changed:
                changed_rows += 1
                file_changed = True

        after_votes = [
            tuple(row.get(field) for field in ("county", "dem_votes", "rep_votes", "other_votes", "total_votes"))
            for row in current.get("rows", [])
        ]
        if before_votes != after_votes:
            vote_changes += 1
        if not file_changed:
            continue

        write(path, current)
        changed_files += 1
        year = str(current.get("year"))
        contest = str(current.get("contest") or "")
        results = (
            aggregate.get("results_by_year", {})
            .get(year, {})
            .get(contest, {})
            .get("statewide", {})
            .get("results", {})
        )
        for row in current.get("rows", []):
            node = results.get(str(row.get("county") or "").upper())
            if not node:
                continue
            for field in CANDIDATE_FIELDS:
                node[field] = row.get(field) or ""

    if vote_changes:
        raise RuntimeError(f"candidate restoration changed votes in {vote_changes} files")
    write(AGGREGATE, aggregate)
    print(f"changed_files={changed_files}")
    print(f"changed_rows={changed_rows}")
    print("vote_changes=0")


if __name__ == "__main__":
    main()

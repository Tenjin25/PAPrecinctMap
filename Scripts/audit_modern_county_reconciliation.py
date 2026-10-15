"""Report district changes from county-controlled modern rebuilds."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "district_contests"
FIELDS = ("dem_votes", "rep_votes", "other_votes", "total_votes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--year", type=int, action="append")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude contest:year")
    parser.add_argument("--ref", help="Compare with data/district_contests at this Git ref")
    args = parser.parse_args()
    rows = []
    for directory in args.candidate:
        for path in sorted(directory.glob("*.json")):
            if path.name == "manifest.json" or not (PUBLISHED / path.name).exists():
                continue
            new = json.loads(path.read_text(encoding="utf-8"))
            if args.ref:
                raw = subprocess.check_output(
                    ["git", "show", f"{args.ref}:data/district_contests/{path.name}"],
                    cwd=ROOT,
                )
                old = json.loads(raw)
            else:
                old = json.loads((PUBLISHED / path.name).read_text(encoding="utf-8"))
            if args.year and int(new.get("year") or 0) not in set(args.year):
                continue
            if f'{new.get("contest_type")}:{new.get("year")}' in set(args.exclude):
                continue
            for district, new_row in new["general"]["results"].items():
                old_row = old["general"]["results"][district]
                deltas = {field: int(new_row[field]) - int(old_row[field]) for field in FIELDS}
                if not any(deltas.values()):
                    continue
                rows.append({
                    "year": new["year"], "contest": new["contest_type"], "scope": new["scope"],
                    "district": district,
                    **{f"old_{field}": old_row[field] for field in FIELDS},
                    **{f"new_{field}": new_row[field] for field in FIELDS},
                    **{f"delta_{field}": deltas[field] for field in FIELDS},
                    "old_margin_pct": old_row["margin_pct"], "new_margin_pct": new_row["margin_pct"],
                })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys() if rows else ["year"])
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "changed_district_rows": len(rows),
        "groups": len({(row["year"], row["contest"], row["scope"]) for row in rows}),
        "largest_absolute_total_changes": sorted(rows, key=lambda row: abs(row["delta_total_votes"]), reverse=True)[:20],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

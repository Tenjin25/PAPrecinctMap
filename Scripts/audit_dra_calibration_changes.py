"""Write district-level before/after deltas for DRA/RDH calibrations."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path


FIELDS = ("dem_votes", "rep_votes", "other_votes", "total_votes")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.path.as_posix()
    old = json.loads(subprocess.run(
        ["git", "show", f"{args.ref}:{source}"], check=True,
        capture_output=True, text=True, encoding="utf-8",
    ).stdout)
    new = json.loads(args.path.read_text(encoding="utf-8"))
    old_rows = old["general"]["results"]
    new_rows = new["general"]["results"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        names = ["district"]
        for field in FIELDS:
            names.extend((f"old_{field}", f"new_{field}", f"delta_{field}"))
        names.extend(("old_margin_pct", "new_margin_pct", "delta_margin_pct"))
        writer = csv.DictWriter(handle, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for district in sorted(new_rows, key=lambda value: int(value)):
            before, after = old_rows[district], new_rows[district]
            row = {"district": district}
            for field in FIELDS:
                row[f"old_{field}"] = int(before[field])
                row[f"new_{field}"] = int(after[field])
                row[f"delta_{field}"] = int(after[field]) - int(before[field])
            old_margin = float(before["margin_pct"])
            new_margin = float(after["margin_pct"])
            row.update({
                "old_margin_pct": f"{old_margin:.6f}",
                "new_margin_pct": f"{new_margin:.6f}",
                "delta_margin_pct": f"{new_margin - old_margin:.6f}",
            })
            writer.writerow(row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

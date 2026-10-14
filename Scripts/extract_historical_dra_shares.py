"""Extract reproducible district vote shares from a reviewed historical JSON."""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ref", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    raw = subprocess.run(
        ["git", "show", f"{args.ref}:{args.source}"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    payload = json.loads(raw)
    results = payload["general"]["results"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["ID", "Dem", "Rep", "Oth"])
        for district in sorted(results, key=lambda value: int(value)):
            row = results[district]
            total = int(row["total_votes"])
            writer.writerow([
                district,
                f'{int(row["dem_votes"]) / total:.12f}',
                f'{int(row["rep_votes"]) / total:.12f}',
                f'{int(row["other_votes"]) / total:.12f}',
            ])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

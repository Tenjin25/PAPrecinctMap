"""Apply reviewed official county controls to published county contest slices."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def key(value) -> str:
    return " ".join(str(value or "").upper().replace(" COUNTY", "").split())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    args = parser.parse_args()
    for year in args.years:
        for benchmark in sorted((DATA / "benchmarks").glob(f"pa_county_{year}_*_certified.csv")):
            contest = benchmark.stem[len(f"pa_county_{year}_"):-len("_certified")]
            target = DATA / "contests" / f"{contest}_{year}.json"
            if not target.exists():
                continue
            with benchmark.open(newline="", encoding="utf-8-sig") as handle:
                controls = {key(row["county"]): row for row in csv.DictReader(handle)}
            document = json.loads(target.read_text(encoding="utf-8"))
            rows = document.get("rows") or []
            if {key(row.get("county")) for row in rows} != set(controls):
                raise RuntimeError(f"county coverage mismatch: {target}")
            changed = 0
            for row in rows:
                control = controls[key(row.get("county"))]
                before = tuple(int(row.get(field) or 0) for field in ("dem_votes", "rep_votes", "other_votes"))
                after = tuple(int(control[field]) for field in ("dem_votes", "rep_votes", "other_votes"))
                changed += before != after
                row.update(zip(("dem_votes", "rep_votes", "other_votes"), after))
                dem, rep, other = after
                total, margin = dem + rep + other, dem - rep
                row.update({
                    "total_votes": total, "winner": "D" if margin > 0 else "R" if margin < 0 else "T",
                    "margin": float(abs(margin)), "margin_pct": abs(margin) / total * 100 if total else 0.0,
                })
            document["meta"] = {
                "source": "Pennsylvania official county returns API",
                "county_control": benchmark.relative_to(DATA).as_posix(),
                "write_ins_excluded": True,
            }
            target.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"{target.relative_to(ROOT)}: changed_counties={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Copy authoritative county vote totals into whole-county House districts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
WHOLE_COUNTY_DISTRICTS = {
    "67": ("MCKEAN", "POTTER", "CAMERON"),
    "78": ("FULTON", "BEDFORD"),
    "109": ("COLUMBIA",),
    "122": ("CARBON",),
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload, *, compact: bool = False):
    if compact:
        text = json.dumps(payload, separators=(",", ":"))
    else:
        text = json.dumps(payload, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def refresh_derived(row):
    dem = int(row.get("dem_votes") or 0)
    rep = int(row.get("rep_votes") or 0)
    other = int(row.get("other_votes") or 0)
    total = dem + rep + other
    margin = dem - rep
    row["total_votes"] = total
    row["winner"] = "D" if dem > rep else "R" if rep > dem else "T"
    row["margin"] = float(abs(margin))
    row["margin_pct"] = abs(margin) / total * 100 if total else 0.0


def enforce_year(year: int):
    for district_path in sorted((DATA / "district_contests").glob(f"state_house_*_{year}.json")):
        payload = load(district_path)
        contest = payload.get("contest_type")
        county_path = DATA / "contests" / f"{contest}_{year}.json"
        if not county_path.exists():
            continue
        county_rows = {
            str(row.get("county", "")).upper(): row
            for row in load(county_path).get("rows", [])
        }
        rows = payload.get("general", {}).get("results", {})
        if not all(
            district in rows and all(county in county_rows for county in county_names)
            for district, county_names in WHOLE_COUNTY_DISTRICTS.items()
        ):
            continue
        changed = False
        for district, county_names in WHOLE_COUNTY_DISTRICTS.items():
            exact = {
                field: sum(int(county_rows[county].get(field) or 0) for county in county_names)
                for field in ("dem_votes", "rep_votes", "other_votes")
            }
            if all(int(rows[district].get(field) or 0) == value for field, value in exact.items()):
                continue
            for field in ("dem_votes", "rep_votes", "other_votes"):
                rows[district][field] = exact[field]
            refresh_derived(rows[district])
            changed = True
        if not changed:
            continue
        source = payload.setdefault("meta", {}).get("source", "")
        marker = "coterminous_county_control"
        if marker not in source:
            payload["meta"]["source"] = f"{source}+{marker}" if source else marker
        write(district_path, payload)
        print(f"updated {district_path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    args = parser.parse_args()
    for year in args.years:
        enforce_year(year)


if __name__ == "__main__":
    main()

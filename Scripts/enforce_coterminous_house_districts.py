#!/usr/bin/env python3
"""Snap coterminous House geometry and conserve statewide contest totals."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PAIRS = {"CARBON": "122", "COLUMBIA": "109"}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, payload, *, compact: bool = False):
    if compact:
        text = json.dumps(payload, separators=(",", ":"))
    else:
        text = json.dumps(payload, indent=2)
    path.write_text(text + "\n", encoding="utf-8")


def allocate_to_target(rows, field: str, fixed_ids: set[str], target: int):
    fixed_total = sum(int(rows[district].get(field) or 0) for district in fixed_ids)
    adjustable_ids = [district for district in rows if district not in fixed_ids]
    adjustable_target = target - fixed_total
    current = sum(int(rows[district].get(field) or 0) for district in adjustable_ids)
    if adjustable_target < 0 or (current == 0 and adjustable_target):
        raise RuntimeError(f"cannot reconcile {field}: target={target} fixed={fixed_total}")
    if current == 0:
        return
    exact = {
        district: int(rows[district].get(field) or 0) * adjustable_target / current
        for district in adjustable_ids
    }
    allocated = {district: math.floor(value) for district, value in exact.items()}
    remainder = adjustable_target - sum(allocated.values())
    order = sorted(adjustable_ids, key=lambda district: (exact[district] - allocated[district], district), reverse=True)
    for district in order[:remainder]:
        allocated[district] += 1
    for district, value in allocated.items():
        rows[district][field] = value


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


def snap_geometry():
    county_path = DATA / "pa_counties.geojson"
    house_path = DATA / "tileset" / "pa_state_house_2022_lines_tileset.geojson"
    counties = load(county_path)
    house = load(house_path)
    county_geometry = {
        str(feature["properties"].get("NAME20") or feature["properties"].get("county")).upper(): feature["geometry"]
        for feature in counties["features"]
    }
    for feature in house["features"]:
        district = str(feature["properties"].get("SLDLST") or feature["properties"].get("id"))
        for county, paired_district in PAIRS.items():
            if district == paired_district:
                feature["geometry"] = county_geometry[county]
    write(house_path, house, compact=True)


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
        if not all(county in county_rows and district in rows for county, district in PAIRS.items()):
            continue
        for county, district in PAIRS.items():
            for field in ("dem_votes", "rep_votes", "other_votes"):
                rows[district][field] = int(county_rows[county].get(field) or 0)
        fixed_ids = set(PAIRS.values())
        for field in ("dem_votes", "rep_votes", "other_votes"):
            statewide_target = sum(int(row.get(field) or 0) for row in county_rows.values())
            allocate_to_target(rows, field, fixed_ids, statewide_target)
        for row in rows.values():
            refresh_derived(row)
        source = payload.setdefault("meta", {}).get("source", "")
        marker = "coterminous_county_control+statewide_vote_control"
        if marker not in source:
            payload["meta"]["source"] = f"{source}+{marker}" if source else marker
        write(district_path, payload)
        print(f"updated {district_path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, required=True)
    parser.add_argument("--skip-geometry", action="store_true")
    args = parser.parse_args()
    if not args.skip_geometry:
        snap_geometry()
    for year in args.years:
        enforce_year(year)


if __name__ == "__main__":
    main()

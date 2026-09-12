#!/usr/bin/env python3
"""Audit geometry and vote totals for whole-county House districts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union

from enforce_coterminous_house_districts import WHOLE_COUNTY_DISTRICTS

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VOTE_FIELDS = ("dem_votes", "rep_votes", "other_votes", "total_votes")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def geometry_rows(threshold: float):
    counties = load_json(DATA / "pa_counties.geojson")["features"]
    districts = load_json(DATA / "tileset" / "pa_state_house_2022_lines_tileset.geojson")["features"]
    county_geometries = {
        str(feature["properties"].get("NAME20") or feature["properties"].get("county")).upper(): shape(feature["geometry"])
        for feature in counties
    }
    district_geometries = {
        str(feature["properties"].get("SLDLST") or feature["properties"].get("id")): shape(feature["geometry"])
        for feature in districts
    }
    rows = []
    for district, county_names in WHOLE_COUNTY_DISTRICTS.items():
        county_geometry = unary_union([county_geometries[county] for county in county_names])
        district_geometry = district_geometries[district]
        intersection = county_geometry.intersection(district_geometry).area
        county_coverage = intersection / county_geometry.area
        district_coverage = intersection / district_geometry.area
        if county_coverage < threshold or district_coverage < threshold:
            raise RuntimeError(f"HD-{district} geometry failed: county={county_coverage:.4%} district={district_coverage:.4%}")
        rows.append((district, county_names, county_coverage, district_coverage))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.999)
    parser.add_argument("--show-matches", action="store_true")
    args = parser.parse_args()

    geometry = geometry_rows(args.threshold)
    print("whole_county_districts", len(geometry))
    for district, counties, county_coverage, district_coverage in geometry:
        print(f"district=HD-{district} counties={','.join(counties)} county_coverage={county_coverage:.4%} district_coverage={district_coverage:.4%}")

    discrepancies = 0
    for district_path in sorted((DATA / "district_contests").glob("state_house_*.json")):
        district_payload = load_json(district_path)
        contest = district_payload.get("contest_type")
        year = district_payload.get("year")
        county_path = DATA / "contests" / f"{contest}_{year}.json"
        if not county_path.exists():
            continue
        county_rows = {str(row.get("county", "")).upper(): row for row in load_json(county_path).get("rows", [])}
        district_rows = district_payload.get("general", {}).get("results", {})
        for district, counties in WHOLE_COUNTY_DISTRICTS.items():
            if district not in district_rows or not all(county in county_rows for county in counties):
                continue
            expected = {field: sum(int(county_rows[county].get(field) or 0) for county in counties) for field in VOTE_FIELDS}
            actual = district_rows[district]
            deltas = {field: int(actual.get(field) or 0) - expected[field] for field in VOTE_FIELDS}
            if any(deltas.values()):
                discrepancies += 1
                print(f"MISMATCH {year} {contest} HD-{district} {deltas}")
            elif args.show_matches:
                print(f"MATCH {year} {contest} HD-{district}")
    if discrepancies:
        raise SystemExit(f"{discrepancies} whole-county vote discrepancies")
    print("whole_county_vote_discrepancies 0")


if __name__ == "__main__":
    main()

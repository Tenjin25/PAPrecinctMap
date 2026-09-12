#!/usr/bin/env python3
"""Audit vote conservation for counties coterminous with legislative districts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def coterminous_pairs(county_path: Path, district_path: Path, threshold: float):
    counties = load_json(county_path)["features"]
    districts = load_json(district_path)["features"]
    district_geometries = [
        (shape(feature["geometry"]), str(feature["properties"].get("SLDLST") or feature["properties"].get("id")))
        for feature in districts
    ]
    pairs = []
    for county_feature in counties:
        county_geometry = shape(county_feature["geometry"])
        county_name = str(
            county_feature["properties"].get("NAME20")
            or county_feature["properties"].get("county")
        ).upper()
        for district_geometry, district_id in district_geometries:
            if not county_geometry.intersects(district_geometry):
                continue
            intersection_area = county_geometry.intersection(district_geometry).area
            county_coverage = intersection_area / county_geometry.area
            district_coverage = intersection_area / district_geometry.area
            if county_coverage >= threshold and district_coverage >= threshold:
                pairs.append((county_name, district_id, county_coverage, district_coverage))
    return pairs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.98)
    parser.add_argument("--show-matches", action="store_true")
    args = parser.parse_args()

    pairs = coterminous_pairs(
        DATA / "pa_counties.geojson",
        DATA / "tileset" / "pa_state_house_2022_lines_tileset.geojson",
        args.threshold,
    )
    print("coterminous_pairs", len(pairs))
    for county, district, county_coverage, district_coverage in pairs:
        print(
            f"pair county={county} district=HD-{district} "
            f"county_coverage={county_coverage:.4%} district_coverage={district_coverage:.4%}"
        )

    discrepancies = []
    for district_path in sorted((DATA / "district_contests").glob("state_house_*.json")):
        district_payload = load_json(district_path)
        contest = district_payload.get("contest_type")
        year = district_payload.get("year")
        county_path = DATA / "contests" / f"{contest}_{year}.json"
        if not county_path.exists():
            continue
        county_payload = load_json(county_path)
        county_rows = {str(row.get("county", "")).upper(): row for row in county_payload.get("rows", [])}
        district_rows = district_payload.get("general", {}).get("results", {})
        county_statewide = sum(int(row.get("total_votes") or 0) for row in county_rows.values())
        district_statewide = sum(int(row.get("total_votes") or 0) for row in district_rows.values())
        statewide_delta = district_statewide - county_statewide
        for county, district, _, _ in pairs:
            county_row = county_rows.get(county)
            district_row = district_rows.get(district)
            if not county_row or not district_row:
                continue
            deltas = {
                field: int(district_row.get(field) or 0) - int(county_row.get(field) or 0)
                for field in ("dem_votes", "rep_votes", "other_votes", "total_votes")
            }
            if any(deltas.values()) or args.show_matches:
                discrepancies.append(
                    (year, contest, county, district, deltas, statewide_delta, district_payload.get("meta", {}).get("source", ""))
                )

    for year, contest, county, district, deltas, statewide_delta, source in discrepancies:
        print(
            f"{year} {contest} {county}/HD-{district} "
            f"dem_delta={deltas['dem_votes']:+d} rep_delta={deltas['rep_votes']:+d} "
            f"other_delta={deltas['other_votes']:+d} total_delta={deltas['total_votes']:+d} "
            f"statewide_delta={statewide_delta:+d} source={source}"
        )


if __name__ == "__main__":
    main()

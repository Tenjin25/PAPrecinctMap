"""Build a VTD20-to-current-precinct geometry crosswalk.

The historical/modern election crosswalks target the VTD20 layer, while the
frontend displays ``pa_current_voting_districts.geojson``.  This bridge maps
each VTD20 target onto the actual current precinct polygons, using exact
VTD20 identity where available and polygon overlap for changed boundaries.
"""

from __future__ import annotations

import csv
from pathlib import Path

import geopandas as gpd


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
OLD_GEOMETRY = DATA / "Voting_Precincts.geojson"
CURRENT_GEOMETRY = DATA / "pa_current_voting_districts.geojson"
OUTPUT = DATA / "crosswalks" / "pa_vtd20_to_current_precinct.csv"


def norm(value: object, width: int = 0) -> str:
    text = "" if value is None else str(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(width) if digits else ""


def main() -> None:
    old = gpd.read_file(OLD_GEOMETRY).to_crs(5070)
    current = gpd.read_file(CURRENT_GEOMETRY).to_crs(5070)
    old["countyfp"] = old["COUNTYFP20"].map(lambda v: norm(v, 3))
    old["vtd20"] = old["VTD"].map(lambda v: norm(v, 6))
    current["countyfp"] = current["COUNTYFP"].map(lambda v: norm(v, 3))
    current["vtd"] = current["VTD"].map(lambda v: norm(v, 6))
    current["vtd20"] = current["VTD20"].map(lambda v: norm(v, 6))
    current["precinct_norm"] = current["precinct_norm"].astype(str).str.upper().str.strip()

    direct = {}
    for row in current.itertuples():
        if row.countyfp and row.vtd20 and row.precinct_norm:
            direct.setdefault((row.countyfp, row.vtd20), []).append((row.countyfp, row.vtd, row.precinct_norm))

    spatial_index = current.sindex
    rows = []
    unmatched = []
    for old_row in old.itertuples():
        key = (old_row.countyfp, old_row.vtd20)
        direct_targets = direct.get(key, [])
        if direct_targets:
            for countyfp, vtd, precinct_norm in direct_targets:
                rows.append({
                    "countyfp": old_row.countyfp,
                    "vtd20": old_row.vtd20,
                    "current_countyfp": countyfp,
                    "current_vtd": vtd,
                    "current_precinct_norm": precinct_norm,
                    "weight": "1.000000000000",
                    "method": "vtd20_identity",
                })
            continue

        candidates = spatial_index.query(old_row.geometry, predicate="intersects")
        overlaps = []
        for idx in candidates:
            current_row = current.iloc[idx]
            if current_row["countyfp"] != old_row.countyfp:
                continue
            area = old_row.geometry.intersection(current_row.geometry).area
            if area > 0 and current_row["precinct_norm"]:
                overlaps.append((current_row["countyfp"], current_row["vtd"], current_row["precinct_norm"], area))
        total = sum(item[3] for item in overlaps)
        if total <= 0:
            unmatched.append(key)
            continue
        for countyfp, vtd, precinct_norm, area in overlaps:
            rows.append({
                "countyfp": old_row.countyfp,
                "vtd20": old_row.vtd20,
                "current_countyfp": countyfp,
                "current_vtd": vtd,
                "current_precinct_norm": precinct_norm,
                "weight": f"{area / total:.12f}",
                "method": "geometry_overlap",
            })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "countyfp", "vtd20", "current_countyfp", "current_vtd",
            "current_precinct_norm", "weight", "method",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):,} bridge rows for {len(set((r['countyfp'], r['vtd20']) for r in rows)):,} VTD20 precincts")
    print(f"unmatched VTD20 precincts: {len(unmatched):,}")


if __name__ == "__main__":
    main()

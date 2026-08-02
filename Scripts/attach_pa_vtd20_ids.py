"""Attach the app's Census VTD20 identifiers to current state polygons."""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry import shape
from shapely.strtree import STRtree


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CURRENT = DATA / "pa_current_voting_districts.geojson"
VTD20 = DATA / "Voting_Precincts.geojson"


def main() -> None:
    current = json.loads(CURRENT.read_text(encoding="utf-8"))
    reference = json.loads(VTD20.read_text(encoding="utf-8"))
    ref_features = reference.get("features", [])
    ref_geometries = [shape(f["geometry"]) for f in ref_features]
    tree = STRtree(ref_geometries)
    matched = 0

    for feature in current.get("features", []):
        geometry = shape(feature["geometry"])
        best_index = None
        best_area = 0.0
        for candidate in tree.query(geometry):
            candidate_index = int(candidate)
            overlap = geometry.intersection(ref_geometries[candidate_index]).area
            if overlap > best_area:
                best_area = overlap
                best_index = candidate_index
        if best_index is None or best_area <= 0:
            continue
        source = ref_features[best_index].get("properties", {})
        props = feature.setdefault("properties", {})
        county = str(source.get("county_nam") or source.get("county_norm") or "").strip().upper()
        vtd = str(source.get("VTD") or source.get("VTDST") or source.get("prec_id") or "").strip()
        if not county or not vtd:
            continue
        props.update(
            {
                "VTD20": vtd,
                "VTD": vtd,
                "VTDST": vtd,
                "prec_id": vtd,
                "county_nam": county,
                "county_norm": county,
                "precinct_norm": f"{county} - {vtd}",
            }
        )
        matched += 1

    CURRENT.write_text(json.dumps(current, separators=(",", ":")), encoding="utf-8")
    print(f"attached VTD20 IDs to {matched:,} of {len(current.get('features', [])):,} current polygons")


if __name__ == "__main__":
    main()

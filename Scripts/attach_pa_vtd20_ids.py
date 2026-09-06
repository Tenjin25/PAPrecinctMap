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
        props = feature.setdefault("properties", {})
        county_fips = str(props.get("COUNTYFP") or props.get("COUNTY") or "").strip().zfill(3)
        local_vtd = "".join(
            ch for ch in str(props.get("VTD_RAW", "")).strip().upper() if ch.isalnum()
        ).zfill(3)
        current_vtd = f"{county_fips}{local_vtd}"
        geometry = shape(feature["geometry"])
        best_index = None
        best_area = 0.0
        for candidate in tree.query(geometry):
            candidate_index = int(candidate)
            candidate_props = ref_features[candidate_index].get("properties", {})
            if str(candidate_props.get("COUNTYFP20") or "").zfill(3) != county_fips:
                continue
            overlap = geometry.intersection(ref_geometries[candidate_index]).area
            if overlap > best_area:
                best_area = overlap
                best_index = candidate_index
        if best_index is None or best_area <= 0:
            continue
        source = ref_features[best_index].get("properties", {})
        county = str(source.get("county_nam") or source.get("county_norm") or "").strip().upper()
        vtd20 = str(source.get("VTD") or source.get("VTDST") or source.get("prec_id") or "").strip()
        if not county or not vtd20 or not current_vtd:
            continue
        props.update(
            {
                "VTD20": vtd20,
                "VTD": current_vtd,
                "VTDST": current_vtd,
                "prec_id": current_vtd,
                "county_nam": county,
                "county_norm": county,
                "precinct_norm": f"{county} - {current_vtd}",
            }
        )
        matched += 1

    CURRENT.write_text(json.dumps(current, separators=(",", ":")), encoding="utf-8")
    print(f"attached VTD20 IDs to {matched:,} of {len(current.get('features', [])):,} current polygons")


if __name__ == "__main__":
    main()

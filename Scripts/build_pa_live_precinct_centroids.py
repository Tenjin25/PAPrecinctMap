"""Build live precinct centroids from the current precinct polygons."""

from __future__ import annotations

import json
import re
from pathlib import Path

from shapely.geometry import shape


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POLYGONS = DATA / "pa_current_voting_districts.geojson"
OUTPUT = DATA / "pa_live_voting_districts_current_centroids.geojson"


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 .-]", "", str(value or "").upper())).strip()


def main() -> None:
    polygons = json.loads(POLYGONS.read_text(encoding="utf-8"))
    features = []
    for feature in polygons.get("features", []):
        props = feature.get("properties", {})
        county = norm(props.get("county_nam") or props.get("county_norm") or props.get("COUNTYFP20"))
        vtd = str(props.get("VTD") or props.get("VTDST") or props.get("prec_id") or "").strip()
        vtd = re.sub(r"[^A-Z0-9]", "", vtd.upper()).zfill(6)
        name = norm(props.get("precinct_name") or props.get("NAME") or vtd)
        point = shape(feature.get("geometry")).representative_point()
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [point.x, point.y]},
            "properties": {
                **props,
                "VTD": vtd,
                "VTDST": vtd,
                "prec_id": vtd,
                "precinct_name": name,
                "precinct_full_name": name,
                "precinct_norm": norm(f"{county} - {vtd}"),
                "county_nam": county,
                "county_norm": county,
                "has_polygon": True,
            },
        })
    OUTPUT.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {len(features):,} centroids to {OUTPUT}")


if __name__ == "__main__":
    main()

"""Download Pennsylvania's current statewide voting-district layer."""

from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
URL = (
    "https://gis.dep.pa.gov/depgisprd/rest/services/"
    "emappa/eMapPA_External/FeatureServer/336/query"
)
OUTPUT = ROOT / "data" / "pa_current_voting_districts.geojson"
COUNTIES = ROOT / "data" / "pa_counties.geojson"
PAGE_SIZE = 1000


def fetch(params: dict[str, object]) -> dict:
    query = urlencode(params)
    with urlopen(f"{URL}?{query}", timeout=120) as response:
        return json.load(response)


def main() -> None:
    features: list[dict] = []
    offset = 0
    while True:
        payload = fetch(
            {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": PAGE_SIZE,
                "resultOffset": offset,
                "f": "geojson",
            }
        )
        page = payload.get("features", [])
        if not page:
            break
        features.extend(page)
        print(f"downloaded {len(features):,} features")
        if len(page) < PAGE_SIZE:
            break
        offset += len(page)
        time.sleep(0.2)

    if not features:
        raise RuntimeError("The state GIS service returned no voting districts")

    counties = json.loads(COUNTIES.read_text(encoding="utf-8"))
    county_names = {
        str(f.get("properties", {}).get("COUNTYFP20", "")).zfill(3): str(
            f.get("properties", {}).get("county")
            or f.get("properties", {}).get("NAME20", "")
        ).strip().upper()
        for f in counties.get("features", [])
    }
    for feature in features:
        props = feature.setdefault("properties", {})
        county_fips = str(props.get("COUNTY", "")).strip().zfill(3)
        local_vtd = "".join(ch for ch in str(props.get("VTD", "")) if ch.isdigit()).zfill(3)
        vtd = f"{county_fips}{local_vtd}"
        county = county_names.get(county_fips, county_fips)
        name = " ".join(str(props.get("NAME", "")).split()).upper()
        props.update(
            {
                "COUNTYFP": county_fips,
                "VTD_RAW": props.get("VTD", ""),
                "VTD": vtd,
                "VTDST": vtd,
                "prec_id": vtd,
                "precinct_name": name or vtd,
                "precinct_full_name": name or vtd,
                "precinct_norm": f"{county} - {vtd}",
                "county_nam": county,
                "county_norm": county,
            }
        )

    OUTPUT.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "name": "pa_current_voting_districts",
                "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
                "features": features,
            },
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(features):,} features to {OUTPUT}")


if __name__ == "__main__":
    main()

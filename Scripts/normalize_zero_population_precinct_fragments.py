"""Normalize current-map fragments that contain no Census population or housing.

These are geometry artifacts, not precincts with missing election returns.  Two
fragments belong to a populated parent precinct; the land-only Adamstown piece
in Berks County has no reported Berks election precinct and is omitted from the
precinct overlay.
"""

from __future__ import annotations

import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
GEOMETRY = BASE / "data" / "pa_current_voting_districts.geojson"
MANIFEST = BASE / "data" / "precinct_returns_manifest.json"

ALIASES = {
    # The CD-167 sliver is part of Radnor Ward 3 Precinct 1.  Its populated
    # companion polygon is 0452360.
    "DELAWARE - 0452345": {
        "VTD": "0452360",
        "VTDST": "0452360",
        "prec_id": "0452360",
        "NAME": "RADNOR TWP WD 03 PCT 01",
        "precinct_name": "RADNOR TWP WD 03 PCT 01",
        "precinct_full_name": "RADNOR TWP WD 03 PCT 01",
        "precinct_norm": "DELAWARE - 0452360",
    },
    # Philadelphia's official current division layer places 94.3% of this
    # zero-population state-layer sliver in Division 49-13.
    "PHILADELPHIA - 1014903": {
        "VTD": "1014913",
        "VTDST": "1014913",
        "prec_id": "1014913",
        "NAME": "PHILADELPHIA WD 49 PCT 13",
        "precinct_name": "PHILADELPHIA WD 49 PCT 13",
        "precinct_full_name": "PHILADELPHIA WD 49 PCT 13",
        "precinct_norm": "PHILADELPHIA - 1014913",
    },
}

OMIT = {"BERKS - 011010"}


def main() -> None:
    payload = json.loads(GEOMETRY.read_text(encoding="utf-8"))
    found: set[str] = set()
    output = []
    for feature in payload.get("features", []):
        properties = feature.get("properties") or {}
        key = str(properties.get("precinct_norm") or "").strip().upper()
        if key in OMIT:
            found.add(key)
            continue
        if key in ALIASES:
            properties.update(ALIASES[key])
            feature["properties"] = properties
            found.add(key)
        output.append(feature)
    expected = set(ALIASES) | OMIT
    if found != expected:
        raise RuntimeError(f"Expected zero-population fragments not found: {sorted(expected - found)}")
    payload["features"] = output
    GEOMETRY.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    frontend = manifest.get("frontend_geometry") or {}
    frontend["features"] = len(output)
    frontend["features_with_precinct_norm"] = sum(
        bool((feature.get("properties") or {}).get("precinct_norm")) for feature in output
    )
    manifest["frontend_geometry"] = frontend
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Normalized {len(ALIASES)} zero-population fragments and omitted {len(OMIT)} land-only artifact")


if __name__ == "__main__":
    main()

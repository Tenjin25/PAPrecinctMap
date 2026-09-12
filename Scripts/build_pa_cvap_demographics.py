#!/usr/bin/env python3
"""Build Pennsylvania CVAP demographic assets from the Census special tabulation."""

from __future__ import annotations

import argparse
import csv
import io
import json
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "pa_cvap_2024.json"
SOURCE_URL = "https://www2.census.gov/programs-surveys/decennial/rdo/datasets/2024/2024-cvap/CVAP_2020-2024_ACS_csv_files.zip"
FILES = {
    "counties": "County.csv",
    "congressional": "CD.csv",
    "state_house": "SLDLC.csv",
    "state_senate": "SLDUC.csv",
}
LINE_GROUPS = {
    "native": (3,),
    "asian": (4,),
    "black": (5,),
    "pacific": (6,),
    "white": (7,),
    "multiracial": (8, 9, 10, 11, 12),
    "hispanic": (13,),
}


def open_source(path: Path | None):
    if path:
        return path.read_bytes()
    with urllib.request.urlopen(SOURCE_URL) as response:
        return response.read()


def geography_id(scope: str, geoid: str):
    marker = "US42"
    if marker not in geoid:
        return None
    suffix = geoid.split(marker, 1)[1]
    if scope == "counties":
        return suffix[:3]
    return str(int(suffix))


def build_scope(archive: zipfile.ZipFile, scope: str):
    grouped = defaultdict(dict)
    names = {}
    with archive.open(FILES[scope]) as raw:
        reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig"))
        for source_row in reader:
            geo_id = geography_id(scope, source_row.get("geoid", ""))
            if geo_id is None:
                continue
            line = int(source_row["lnnumber"])
            grouped[geo_id][line] = source_row
            names[geo_id] = source_row["geoname"]

    output = {}
    for geo_id, lines in grouped.items():
        total_line = lines[1]
        total_cvap = int(total_line["cvap_est"])
        row = {
            "district": int(geo_id) if scope != "counties" else None,
            "name": names[geo_id],
            "geoid": total_line["geoid"],
            "total_population": int(total_line["tot_est"]),
            "adult_population": int(total_line["adu_est"]),
            "citizen_population": int(total_line["cit_est"]),
            "cvap_total": total_cvap,
            "cvap_total_24": total_cvap,
            "cvap_moe": int(total_line["cvap_moe"]),
            "source_vintage": "2020-2024 ACS CVAP",
        }
        for label, line_numbers in LINE_GROUPS.items():
            estimate = sum(int(lines[number]["cvap_est"]) for number in line_numbers)
            row[f"{label}_cvap"] = estimate
            row[f"{label}_cvap_pct"] = round(estimate * 100 / total_cvap, 2) if total_cvap else 0.0
            row[f"{label}_vap_pct"] = row[f"{label}_cvap_pct"]
        output[geo_id] = row
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    source_bytes = open_source(args.source_zip)
    with zipfile.ZipFile(io.BytesIO(source_bytes)) as archive:
        scopes = {scope: build_scope(archive, scope) for scope in FILES}

    counties = {}
    for county_fips, row in scopes["counties"].items():
        county_name = row["name"].split(" County,", 1)[0].upper()
        row["county_fips"] = county_fips
        row["county"] = county_name.title()
        counties[county_name] = row

    payload = {
        "meta": {
            "source": "U.S. Census Bureau CVAP Special Tabulation",
            "vintage": "2020-2024 ACS 5-Year",
            "geography": "2024 counties and state legislative districts; 119th Congress",
            "source_url": SOURCE_URL,
        },
        "counties": counties,
        "congressional": list(scopes["congressional"].values()),
        "state_house": list(scopes["state_house"].values()),
        "state_senate": list(scopes["state_senate"].values()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")

    csv_outputs = {
        "county": list(counties.values()),
        "congressional": payload["congressional"],
        "state_house": payload["state_house"],
        "state_senate": payload["state_senate"],
    }
    for label, rows in csv_outputs.items():
        csv_path = args.output.with_name(f"pa_cvap_2024_{label}.csv")
        fieldnames = list(rows[0].keys())
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
    print(
        f"wrote {args.output} counties={len(counties)} congressional={len(payload['congressional'])} "
        f"state_house={len(payload['state_house'])} state_senate={len(payload['state_senate'])}"
    )


if __name__ == "__main__":
    main()

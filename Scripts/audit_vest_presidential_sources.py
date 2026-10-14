#!/usr/bin/env python3
"""Compare generic PA presidential feeds with VEST at precinct and county level."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_pa_data_layers as layers  # noqa: E402

VEST_FIELDS = {
    2016: (("G16PREDCLI",), ("G16PRERTRU",), ("G16PRELJOH", "G16PREGSTE", "G16PRECCAS")),
    2020: (("G20PREDBID",), ("G20PRERTRU",), ("G20PRELJOR",)),
}


def bucket(party: str) -> str:
    party = str(party or "").strip().upper()
    return "dem" if party.startswith("DEM") else "rep" if party.startswith("REP") else "other"


def county_lookups():
    payload = json.loads((ROOT / "data" / "pa_counties.geojson").read_text(encoding="utf-8"))
    by_fips, by_name = {}, {}
    for feature in payload["features"]:
        props = feature["properties"]
        fips = str(props.get("COUNTYFP20") or props.get("COUNTYFP")).zfill(3)
        name = str(props.get("NAME20") or props.get("NAME")).strip().upper()
        by_fips[fips] = name
        by_name[layers.normalize_county_name(name)] = fips
    return by_fips, by_name


def load_vest(year: int):
    path = (ROOT / "data" / "historical_sources" / f"vest_pa_{year}.zip").resolve()
    frame = gpd.read_file(f"zip://{path.as_posix()}", ignore_geometry=True)
    dem_fields, rep_fields, other_fields = VEST_FIELDS[year]
    result = defaultdict(lambda: defaultdict(int))
    names = {}
    for row in frame.to_dict("records"):
        key = (str(row["COUNTYFP"]).zfill(3), str(row["PRECINCT"]).strip().upper().zfill(6))
        result[key]["dem"] += round(sum(float(row.get(field) or 0) for field in dem_fields))
        result[key]["rep"] += round(sum(float(row.get(field) or 0) for field in rep_fields))
        result[key]["other"] += round(sum(float(row.get(field) or 0) for field in other_fields))
        names[key] = str(row.get("NAME") or "").strip()
    return result, names


def load_generic(year: int, by_name):
    result = defaultdict(lambda: defaultdict(int))
    names = {}
    if year == 2016:
        path = ROOT / "data" / "Openelections" / "2016" / "20161108__pa__general__precinct.csv"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        rows = layers.read_csv_rows(ROOT / "data" / "ElectionReturns_2020_General_PrecinctReturns.txt")
    for row in rows:
        if layers.office_mapping_for_contest(row.get("office") or "") != "president":
            continue
        county_name = layers.normalize_county_name(row.get("county") or "")
        countyfp = by_name.get(county_name, "")
        source_vtd = str(row.get("source_vtd") or "").strip().upper()
        if not source_vtd:
            match = re.search(r"([A-Z0-9]{6})$", str(row.get("precinct") or "").strip().upper())
            source_vtd = match.group(1) if match else ""
        key = (countyfp, source_vtd.zfill(6))
        result[key][bucket(row.get("party"))] += round(float(row.get("votes") or 0))
        names[key] = str(row.get("precinct") or "").strip()
    return result, names


def write_reports(year: int, output: Path):
    by_fips, by_name = county_lookups()
    vest, vest_names = load_vest(year)
    generic, generic_names = load_generic(year, by_name)
    output.mkdir(parents=True, exist_ok=True)
    precinct_path = output / f"vest_generic_president_{year}_precinct.csv"
    county_path = output / f"vest_generic_president_{year}_county.csv"
    summary_path = output / f"vest_generic_president_{year}_summary.json"
    fields = ("dem", "rep", "other")
    county = defaultdict(lambda: defaultdict(int))
    with precinct_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "county_fips", "county", "precinct", "vest_name", "generic_name", "status",
            *[f"vest_{field}" for field in fields], *[f"generic_{field}" for field in fields],
            *[f"delta_{field}" for field in fields], "delta_total",
        ])
        for key in sorted(set(vest) | set(generic)):
            status = "matched"
            if key not in generic:
                status = "missing_from_generic"
            elif key not in vest:
                status = "missing_from_vest"
            deltas = {field: generic[key][field] - vest[key][field] for field in fields}
            if status == "matched" and any(deltas.values()):
                status = "vote_difference"
            for field in fields:
                county[key[0]][f"vest_{field}"] += vest[key][field]
                county[key[0]][f"generic_{field}"] += generic[key][field]
            writer.writerow([
                key[0], by_fips.get(key[0], ""), key[1], vest_names.get(key, ""),
                generic_names.get(key, ""), status,
                *[vest[key][field] for field in fields], *[generic[key][field] for field in fields],
                *[deltas[field] for field in fields], sum(deltas.values()),
            ])
    with county_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "county_fips", "county", *[f"vest_{field}" for field in fields],
            *[f"generic_{field}" for field in fields], *[f"delta_{field}" for field in fields],
            "delta_total",
        ])
        for countyfp in sorted(county):
            values = county[countyfp]
            deltas = {field: values[f"generic_{field}"] - values[f"vest_{field}"] for field in fields}
            writer.writerow([
                countyfp, by_fips.get(countyfp, ""), *[values[f"vest_{field}"] for field in fields],
                *[values[f"generic_{field}"] for field in fields], *[deltas[field] for field in fields],
                sum(deltas.values()),
            ])
    raw_vest = {
        field: sum(values[field] for values in vest.values()) for field in fields
    }
    generic_total = {
        field: sum(values[field] for values in generic.values()) for field in fields
    }
    audit = json.loads((ROOT / "data" / f"vest_{year}_district_vote_audit.json").read_text())
    control = audit["controls"]["president"]
    summary = {
        "year": year,
        "vest_raw": raw_vest,
        "generic": generic_total,
        "production_control": {
            "dem": control["dem_votes"],
            "rep": control["rep_votes"],
            "other": control["other_votes"],
        },
        "generic_minus_production_control": {
            field: generic_total[field] - control[f"{field}_votes"] for field in fields
        },
        "vest_raw_minus_production_control": {
            field: raw_vest[field] - control[f"{field}_votes"] for field in fields
        },
        "precinct_report": str(precinct_path.relative_to(ROOT)),
        "county_report": str(county_path.relative_to(ROOT)),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return precinct_path, county_path, summary_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "district_bef_audit")
    args = parser.parse_args()
    for year in (2016, 2020):
        print(*write_reports(year, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

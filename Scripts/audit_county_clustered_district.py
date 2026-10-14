#!/usr/bin/env python3
"""Emit county/precinct attribution for one county-clustered district result."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Scripts"))

import build_pa_data_layers as layers  # noqa: E402
import build_county_clustered_2024_district_contests as clustered  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--contest", required=True)
    parser.add_argument("--scope", choices=tuple(clustered.SCOPES), default="congressional")
    parser.add_argument("--district", required=True)
    parser.add_argument("--pl-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    maps, _county_districts, _vap_blocks, _carter_blocks = clustered.build_vap_maps(
        args.pl_zip, ROOT / "data" / "BlockAssign_ST42_PA.zip"
    )
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    layers.load_vtd_current_district_blocks = lambda: maps
    source = next(path for year, path in layers.iter_openelections_csvs() if year == args.year)
    rows = clustered.integerize_fractional_rows(layers.read_csv_rows(source))
    match_cache = {}
    details = []
    totals = defaultdict(int)
    county_totals = defaultdict(lambda: defaultdict(int))
    county_fips = layers.county_fips_by_name()
    for row in rows:
        if layers.office_mapping_for_contest(row.get("office") or "") != args.contest:
            continue
        votes = layers.safe_int(row.get("votes"))
        if votes <= 0:
            continue
        county_name = layers.normalize_county_name(row.get("county") or "")
        countyfp = county_fips.get(county_name, "")
        match_key = (
            county_name,
            layers.normalize_bridge_precinct_name(row.get("precinct") or ""),
        )
        maintained = layers.maintained_targets_for_row(row, args.year, countyfp) if countyfp else []
        maintained = [
            target for target in maintained
            if maps.get(args.scope, {}).get((target[0], target[1]))
        ]
        if maintained:
            weighted_vtds = [(county, vtd, weight) for county, vtd, weight, _method in maintained]
            method = "+".join(sorted({item[3] for item in maintained}))
        else:
            if match_key not in match_cache:
                match_cache[match_key] = layers.match_row_to_current_vtds(row)
            weighted_vtds = [(*target, 1.0) for target in match_cache[match_key]]
            method = "current_precinct_or_vtd_name"
        district_counts = defaultdict(float)
        for target_county, target_vtd, target_weight in weighted_vtds:
            for district, weight in maps[args.scope].get((target_county, target_vtd), {}).items():
                district_counts[district] += float(weight) * float(target_weight)
        allocations = layers.allocate_votes_by_block_counts(votes, district_counts)
        allocated = int(allocations.get(str(args.district)) or 0)
        if not allocated:
            continue
        party = (row.get("party") or "").strip().upper()
        bucket = "dem" if party in layers.PARTY_DEM else "rep" if party in layers.PARTY_REP else "other"
        totals[bucket] += allocated
        county_totals[county_name][bucket] += allocated
        details.append({
            "county": county_name,
            "county_fips": countyfp,
            "precinct": row.get("precinct") or "",
            "party": party,
            "candidate": row.get("candidate") or "",
            "source_votes": votes,
            "district_votes": allocated,
            "district_weight": district_counts.get(str(args.district), 0),
            "all_district_weight": sum(district_counts.values()),
            "method": method,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)
    summary = {
        "year": args.year,
        "contest": args.contest,
        "scope": args.scope,
        "district": str(args.district),
        "source": str(source if not source.is_absolute() else source.relative_to(ROOT)),
        "totals": dict(totals),
        "county_totals": {county: dict(values) for county, values in sorted(county_totals.items())},
        "detail": str(args.output if not args.output.is_absolute() else args.output.relative_to(ROOT)),
    }
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

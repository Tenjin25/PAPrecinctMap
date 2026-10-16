#!/usr/bin/env python3
"""Build 2024 statewide contests with exact county clusters and Carter splits.

Whole counties are assigned intact to their sole district.  In counties split by
the Carter plan, election VTDs are allocated with 2020 Census block VAP through
the Carter block assignment file and the official congressional/legislative
block equivalency files.  Integerization remains county scoped, so every
county/party and statewide/party total is conserved exactly.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "Scripts"))

import build_pa_data_layers as layers  # noqa: E402
import build_rdh_2024_district_contests as rdh  # noqa: E402


SCOPES = {
    "congressional": ("42_PA_CD118.txt", "CDFP"),
    "state_house": ("42_PA_SLDL22.txt", "SLDLST"),
    "state_senate": ("42_PA_SLDU22.txt", "SLDUST"),
}
WHOLE_COUNTY_THRESHOLD = 0.999
MATERIAL_PARTIAL_THRESHOLD = 0.001


def classify_county_weights(weights: dict[str, float]) -> set[str]:
    """Return the material districts for a county under the 99.9% rule."""
    total = sum(weights.values())
    if total <= 0:
        return set()
    top_district, top_weight = max(weights.items(), key=lambda item: item[1])
    if top_weight / total >= WHOLE_COUNTY_THRESHOLD:
        return {top_district}
    return {
        district for district, weight in weights.items()
        if weight / total > MATERIAL_PARTIAL_THRESHOLD
    }


def congressional_mail_district(precinct: str) -> str:
    """Extract an explicitly localized congressional-mail district label."""
    match = re.fullmatch(r"(\d+)(?:ST|ND|RD|TH) CD", precinct.strip(), re.IGNORECASE)
    return str(int(match.group(1))) if match else ""


def integerize_fractional_rows(rows: list[dict]) -> list[dict]:
    """Integerize crosswalk rows locally, then reconcile explained roundoff."""
    groups = defaultdict(list)
    original_values = {}
    for index, row in enumerate(rows):
        try:
            value = Decimal(str(row.get("votes") or "0"))
        except Exception:
            value = Decimal(0)
        if value < 0:
            continue
        key = (
            layers.normalize_county_name(row.get("county") or ""),
            layers.office_mapping_for_contest(row.get("office") or ""),
            (row.get("party") or "").strip().upper(),
        )
        groups[key].append((index, value))
        original_values[index] = value
    result = [dict(row) for row in rows]
    for values in groups.values():
        floors = {
            index: int(value.to_integral_value(rounding=ROUND_FLOOR))
            for index, value in values
        }
        target = int(
            sum((value for _index, value in values), Decimal(0)).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        remaining = target - sum(floors.values())
        ranked = sorted(
            values,
            key=lambda item: (
                -(item[1] - item[1].to_integral_value(rounding=ROUND_FLOOR)),
                item[0],
            ),
        )
        for index, _value in ranked[:remaining]:
            floors[index] += 1
        for index, _value in values:
            result[index]["votes"] = str(floors[index])

    # County-level rounding can differ from the statewide rounded source by a
    # handful of votes. Reconcile only that explicit arithmetic difference,
    # using the rows with the greatest signed fractional deficit. This is not
    # an unexplained vote residual and does not use district outcomes.
    statewide_groups = defaultdict(list)
    for index, row in enumerate(rows):
        if index not in original_values:
            continue
        key = (
            layers.office_mapping_for_contest(row.get("office") or ""),
            (row.get("party") or "").strip().upper(),
        )
        statewide_groups[key].append(index)
    for indices in statewide_groups.values():
        target = int(
            sum((original_values[index] for index in indices), Decimal(0)).to_integral_value(
                rounding=ROUND_HALF_UP
            )
        )
        current = sum(int(result[index]["votes"]) for index in indices)
        delta = target - current
        if not delta:
            continue
        ranked = sorted(
            indices,
            key=lambda index: original_values[index] - Decimal(result[index]["votes"]),
            reverse=delta > 0,
        )
        for index in ranked[:abs(delta)]:
            result[index]["votes"] = str(int(result[index]["votes"]) + (1 if delta > 0 else -1))
    return result


def load_block_vap(path: Path) -> dict[str, float]:
    if path.name.endswith(".csv.gz"):
        with gzip.open(path, "rt", encoding="utf-8", newline="") as handle:
            return {
                str(row["block"]).zfill(15): float(row["vap"] or 0)
                for row in csv.DictReader(handle)
            }
    logrec_to_block: dict[str, str] = {}
    with zipfile.ZipFile(path) as archive:
        with io.TextIOWrapper(archive.open("pageo2020.pl"), encoding="latin-1") as handle:
            for row in csv.reader(handle, delimiter="|"):
                if len(row) <= 34 or row[2] != "750":
                    continue
                block = f"{row[12]}{row[14]}{row[32]}{row[34]}"
                if len(block) == 15:
                    logrec_to_block[row[7]] = block
        result: dict[str, float] = {}
        with io.TextIOWrapper(archive.open("pa000022020.pl"), encoding="latin-1") as handle:
            for row in csv.reader(handle, delimiter="|"):
                if len(row) <= 5:
                    continue
                block = logrec_to_block.get(row[4])
                if block:
                    result[block] = float(row[5] or 0)  # P0030001: voting-age population
    return result


def load_carter_vtds(path: Path) -> dict[str, tuple[str, str]]:
    result = {}
    with zipfile.ZipFile(path) as archive:
        with archive.open("BlockAssign_ST42_PA_VTD.txt") as raw:
            next(raw, None)
            for line in raw:
                parts = line.decode("utf-8", errors="ignore").strip().split("|")
                if len(parts) >= 3:
                    result[parts[0]] = (parts[1].zfill(3), parts[2].strip().zfill(6))
    return result


def load_district_assignments() -> dict[str, dict[str, str]]:
    result = {}
    for scope, (filename, field) in SCOPES.items():
        assignments = {}
        with (ROOT / "data" / filename).open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle, skipinitialspace=True):
                assignments[row["GEOID"]] = layers.normalize_district_id(row[field])
        result[scope] = assignments
    return result


def build_vap_maps(pl_zip: Path, baf_zip: Path):
    vap = load_block_vap(pl_zip)
    vtds = load_carter_vtds(baf_zip)
    districts = load_district_assignments()
    maps = {scope: defaultdict(lambda: defaultdict(float)) for scope in SCOPES}
    county_weights = {scope: defaultdict(lambda: defaultdict(float)) for scope in SCOPES}
    missing = defaultdict(int)
    for block, vtd_key in vtds.items():
        weight = vap.get(block, 0.0)
        for scope, assignment in districts.items():
            district = assignment.get(block)
            if not district:
                missing[scope] += 1
                continue
            county_weights[scope][vtd_key[0]][district] += weight
            maps[scope][vtd_key][district] += weight
    if any(missing.values()):
        raise RuntimeError(f"Carter blocks missing BEF districts: {dict(missing)}")
    county_districts = {scope: defaultdict(set) for scope in SCOPES}
    for scope, counties in county_weights.items():
        for county, weights in counties.items():
            total = sum(weights.values())
            if total <= 0:
                continue
            top_district, top_weight = max(weights.items(), key=lambda item: item[1])
            county_districts[scope][county] = classify_county_weights(weights)
            if len(county_districts[scope][county]) == 1 and top_weight / total >= WHOLE_COUNTY_THRESHOLD:
                # Clamp BAF/BEF slivers so the general all-year builder also
                # carries the canonical county total wholly into this district.
                for (vtd_county, _vtd), district_weights in maps[scope].items():
                    if vtd_county == county:
                        vtd_total = sum(district_weights.values())
                        district_weights.clear()
                        district_weights[top_district] = vtd_total
    return maps, county_districts, len(vap), len(vtds)


def preserve_candidate_names(output: Path, published: Path) -> None:
    """Carry reviewed display names forward without changing vote data."""
    for target in output.glob("*.json"):
        source = published / target.name
        if target.name == "manifest.json" or not source.exists():
            continue
        new = json.loads(target.read_text(encoding="utf-8"))
        old = json.loads(source.read_text(encoding="utf-8"))
        new_rows = new.get("general", {}).get("results", {})
        old_rows = old.get("general", {}).get("results", {})
        for district, row in new_rows.items():
            prior = old_rows.get(district, {})
            for field in ("dem_candidate", "rep_candidate"):
                if prior.get(field):
                    row[field] = layers.normalize_candidate_label(prior[field])
        target.write_text(json.dumps(new, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--year", type=int, choices=(2022, 2024), default=2024)
    parser.add_argument("--pl-zip", type=Path)
    parser.add_argument(
        "--block-vap",
        type=Path,
        default=ROOT / "data" / "crosswalks" / "pa_block20_vap.csv.gz",
        help="Retained block/VAP CSV.gz; overridden by --pl-zip when supplied",
    )
    parser.add_argument("--baf-zip", type=Path, default=ROOT / "data" / "BlockAssign_ST42_PA.zip")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--all-years-output", type=Path)
    parser.add_argument(
        "--contests",
        default="us_senate",
        help="Comma-separated contest families for --all-years-output (default: us_senate)",
    )
    parser.add_argument(
        "--years",
        help="Optional comma-separated election years for --all-years-output",
    )
    args = parser.parse_args()

    vap_source = args.pl_zip or args.block_vap
    if not vap_source.exists():
        parser.error(f"block VAP source not found: {vap_source}")
    vap_maps, county_districts, vap_blocks, carter_blocks = build_vap_maps(
        vap_source, args.baf_zip
    )
    if not args.output and not args.all_years_output:
        parser.error("provide --output, --all-years-output, or both")
    if args.output and not args.source:
        parser.error("--output requires --source")

    original_load = layers.load_vtd_current_district_blocks
    original_direct = rdh.direct_districts
    layers.VTD_CURRENT_DISTRICT_BLOCKS = vap_maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = vap_maps
    layers.load_vtd_current_district_blocks = lambda: vap_maps
    rdh.layers.load_vtd_current_district_blocks = lambda: vap_maps

    prefix_scope = {value: key for key, value in rdh.PREFIXES.items()}

    def county_cluster_direct(row, columns, prefix):
        scope = prefix_scope[prefix]
        county = str(row.get("COUNTYFP") or "").strip().zfill(3)
        direct = original_direct(row, columns, prefix)
        # Congressional mail rows carry an explicit CD but no VTD. Keep that
        # local assignment; legislative residuals remain localized within it.
        precinct = str(row.get("Precinct") or "")
        if scope == "congressional":
            mail_cd = congressional_mail_district(precinct)
            if mail_cd:
                return {mail_cd}
            if "Congressional Mail Votes" in precinct:
                return direct
        # Only split counties need modeled block allocation. A whole county is
        # carried intact even when the election row lacks a district-contest vote.
        if len(county_districts[scope].get(county, set())) == 1:
            return set(county_districts[scope][county])
        return set()

    rdh.direct_districts = county_cluster_direct
    old_argv = sys.argv
    try:
        if args.output:
            sys.argv = [
                str(Path(__file__)),
                "--year", str(args.year),
                "--source", str(args.source),
                "--output", str(args.output),
                "--county-controls-dir", str(ROOT / "data" / "benchmarks"),
            ]
            rdh.main()
            preserve_candidate_names(args.output, ROOT / "data" / "district_contests")
        if args.all_years_output:
            # The general builder already routes every source row through the
            # VTD map. Replacing that map with Carter block-VAP weights makes
            # whole counties exact automatically and models only split ones.
            original_embedded = layers.embedded_congressional_district_from_precinct_label
            original_dra_calibration = layers.apply_dra_share_calibration
            original_read_csv_rows = layers.read_csv_rows
            integerized_rows_cache = {}
            layers.embedded_congressional_district_from_precinct_label = lambda _value: ""
            # DRA district shares are useful as a comparison, but replacing
            # party buckets independently by scope violates statewide party
            # conservation.  The block/VAP allocation is the production rule.
            layers.apply_dra_share_calibration = lambda _nodes, _sources: None
            def read_integerized_rows(path):
                cache_key = str(Path(path).resolve())
                if cache_key not in integerized_rows_cache:
                    integerized_rows_cache[cache_key] = integerize_fractional_rows(
                        original_read_csv_rows(path)
                    )
                return integerized_rows_cache[cache_key]

            layers.read_csv_rows = read_integerized_rows
            try:
                contest_types = {
                    value.strip() for value in args.contests.split(",") if value.strip()
                }
                layers.build_district_manifests(
                    args.all_years_output,
                    contest_types=contest_types,
                    years={int(value) for value in args.years.split(",")} if args.years else None,
                )
            finally:
                layers.embedded_congressional_district_from_precinct_label = original_embedded
                layers.apply_dra_share_calibration = original_dra_calibration
                layers.read_csv_rows = original_read_csv_rows
            preserve_candidate_names(args.all_years_output, ROOT / "data" / "district_contests")
    finally:
        sys.argv = old_argv
        rdh.direct_districts = original_direct
        layers.load_vtd_current_district_blocks = original_load

    print({
        "method": "exact whole-county clusters plus Carter BAF/BEF block-VAP splits",
        "whole_county_threshold": WHOLE_COUNTY_THRESHOLD,
        "material_partial_threshold": MATERIAL_PARTIAL_THRESHOLD,
        "vap_blocks": vap_blocks,
        "carter_blocks": carter_blocks,
        "split_counties": {
            scope: sorted(county for county, values in counties.items() if len(values) > 1)
            for scope, counties in county_districts.items()
        },
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

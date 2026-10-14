"""Build audited modern statewide-contest results by current PA districts from RDH.

RDH supplies explicit congressional and state-House contest columns for almost
every precinct row.  State-Senate districts and rows without a district contest
are placed through the maintained precinct -> Census block -> 2022 district
chain in ``build_pa_data_layers``.  Philadelphia's three congressional-mail
rows have no precinct/VTD identifier; their small residual is distributed
within the stated congressional district using the same candidate's regular
Philadelphia precinct votes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import build_pa_data_layers as layers


SCOPES = ("congressional", "state_house", "state_senate")
PREFIXES = {"congressional": "GCON", "state_house": "GSL", "state_senate": "GSU"}
EXPECTED = {"congressional": 17, "state_house": 203, "state_senate": 50}
PARTY_CODES = {
    "Democratic": "DEM",
    "Republican": "REP",
}
CONTEST_BY_CODE = {
    "ATG": "attorney_general",
    "AUD": "auditor",
    "PRE": "president",
    "TRE": "treasurer",
    "USS": "us_senate",
    "GOV": "governor",
}


def value(row, column):
    try:
        return int(float(row.get(column) or 0))
    except (TypeError, ValueError):
        return 0


def read_source(source, year):
    year_code = str(year)[-2:]
    with zipfile.ZipFile(source) as archive:
        readme = archive.read("README.txt").decode("utf-8", errors="replace")
        descriptions = {}
        for line in readme.splitlines():
            match = re.match(r"^(G\S+)\s+(.+?)\s*$", line)
            if match:
                descriptions[match.group(1)] = match.group(2).strip()
        with archive.open(f"pa_{year}_gen_prec.csv") as raw:
            reader = csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
            rows = list(reader)
            columns = reader.fieldnames or []
    statewide = {}
    for column in columns:
        if not re.match(rf"^G{year_code}(?:ATG|AUD|GOV|PRE|TRE|USS)", column):
            continue
        parts = descriptions.get(column, "").split("-:-")
        if len(parts) != 4:
            raise ValueError(f"Missing RDH field description for {column}")
        office, _scope, party_name, candidate = (part.strip() for part in parts)
        code_match = re.match(rf"^G{year_code}([A-Z]{{3}})", column)
        contest = CONTEST_BY_CODE.get(code_match.group(1) if code_match else "")
        if not contest:
            raise ValueError(f"Unknown statewide office for {column}: {office}")
        statewide[column] = {
            "contest": contest,
            "party": PARTY_CODES.get(party_name, party_name.upper()),
            "candidate": layers.normalize_candidate_label(candidate),
        }
    district_columns = {
        scope: [column for column in columns if column.startswith(prefix)]
        for scope, prefix in PREFIXES.items()
    }
    return rows, statewide, district_columns


def direct_districts(row, columns, prefix):
    districts = {
        str(int(match.group(1)))
        for column in columns
        if value(row, column) > 0
        for match in [re.match(rf"^{prefix}(\d+)", column)]
        if match
    }
    return districts


def geometry_allocations(row, block_maps, year):
    countyfp = str(row.get("COUNTYFP") or "").strip().zfill(3)
    source_vtd = str(row.get("VTD code") or "").strip().upper().zfill(6)
    direct_vtd = (countyfp, source_vtd)
    if source_vtd and any(block_maps.get(scope, {}).get(direct_vtd) for scope in SCOPES):
        weighted_vtds = [(countyfp, source_vtd, 1.0)]
        method = "rdh_vtd_code_baf"
    else:
        weighted_vtds = []
        method = ""
    bridge_row = {
        "county": row.get("County") or "",
        # RDH's ``Precinct`` is a county-local numeric ID.  ``Muni_Name`` is
        # the election-geography label used by the maintained modern BEF.
        "precinct": row.get("Muni_Name") or row.get("Precinct") or "",
        "source_vtd": row.get("VTD code") or "",
    }
    if not weighted_vtds:
        targets = layers.maintained_targets_for_row(bridge_row, year, countyfp)
        targets = [
            target for target in targets
            if any(block_maps.get(scope, {}).get((target[0], target[1])) for scope in SCOPES)
        ]
        if targets:
            weighted_vtds = [(county, vtd, weight) for county, vtd, weight, _method in targets]
            method = "maintained_bef_baf_chain"
        else:
            matched = layers.match_row_to_current_vtds(bridge_row)
            weighted_vtds = [(county, vtd, 1.0) for county, vtd in matched]
            method = "current_vtd_name_baf"
    allocations = {}
    for scope in SCOPES:
        counts = defaultdict(float)
        for county, vtd, target_weight in weighted_vtds:
            for district, block_count in (block_maps.get(scope, {}).get((county, vtd)) or {}).items():
                counts[district] += float(block_count) * float(target_weight)
        total = sum(counts.values())
        allocations[scope] = {
            district: count / total for district, count in counts.items()
        } if total else {}
    return allocations, method


def allocate(total, weights):
    weight_total = sum(weights.values())
    if not weight_total:
        return {}
    return {district: total * weight / weight_total for district, weight in weights.items()}


def round_district_vote_components(results):
    """Round once per party across districts while preserving source totals."""
    district_ids = sorted(results, key=int)
    for field in ("dem_votes", "rep_votes", "other_votes"):
        raw = {district: float(results[district].get(field) or 0) for district in district_ids}
        rounded = {district: int(amount) for district, amount in raw.items()}
        remainder = int(round(sum(raw.values()))) - sum(rounded.values())
        order = sorted(
            district_ids,
            key=lambda district: (raw[district] - rounded[district], -int(district)),
            reverse=True,
        )
        for district in order[:remainder]:
            rounded[district] += 1
        for district, amount in rounded.items():
            results[district][field] = amount
    for node in results.values():
        node["total_votes"] = sum(
            int(node.get(field) or 0) for field in ("dem_votes", "rep_votes", "other_votes")
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, choices=(2022, 2024), default=2024)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    source = args.source or ROOT / "data" / f"pa_{args.year}_gen_prec_csv.zip"
    args.output = args.output or ROOT / "data" / f"district_contests_rdh_{args.year}_verified"
    args.output.mkdir(parents=True, exist_ok=True)

    rows, statewide, district_columns = read_source(source, args.year)
    unique_ids = [str(row.get("UNIQUE_ID") or "").strip() for row in rows]
    if not all(unique_ids) or len(unique_ids) != len(set(unique_ids)):
        raise RuntimeError("RDH UNIQUE_ID values are blank or duplicated")
    block_maps = layers.load_vtd_current_district_blocks()
    prepared = []
    method_counts = {scope: Counter() for scope in SCOPES}
    row_failures = {scope: [] for scope in SCOPES}

    for row in rows:
        geometry, geometry_method = geometry_allocations(row, block_maps, args.year)
        direct = {
            scope: direct_districts(row, district_columns[scope], PREFIXES[scope])
            for scope in SCOPES
        }
        allocations = {}
        for scope in SCOPES:
            districts = direct.get(scope) or set()
            if len(districts) == 1:
                allocations[scope] = {next(iter(districts)): 1.0}
                method_counts[scope]["rdh_embedded_district"] += 1
            elif geometry.get(scope):
                allocations[scope] = geometry[scope]
                method_counts[scope][geometry_method] += 1
            else:
                allocations[scope] = {}
                row_failures[scope].append({
                    "county": row.get("County"),
                    "precinct": row.get("Precinct"),
                    "vtd": row.get("VTD code"),
                })
        prepared.append((row, allocations))

    nodes = defaultdict(dict)
    regular_pools = defaultdict(lambda: defaultdict(float))
    party_pools = defaultdict(lambda: defaultdict(float))
    residuals = []
    controls = Counter()
    party_controls = defaultdict(Counter)
    source_rows = Counter()

    for row, row_allocations in prepared:
        cd = next(iter(direct_districts(
            row, district_columns["congressional"], PREFIXES["congressional"]
        )), "")
        for column, info in statewide.items():
            votes = value(row, column)
            if votes <= 0:
                continue
            contest = info["contest"]
            controls[contest] += votes
            bucket = "dem_votes" if info["party"] == "DEM" else "rep_votes" if info["party"] == "REP" else "other_votes"
            party_controls[contest][bucket] += votes
            source_rows[contest] += 1
            for scope in SCOPES:
                weights = row_allocations[scope]
                if not weights:
                    residuals.append((scope, contest, column, info, cd, votes, row))
                    continue
                allocated = allocate(votes, weights)
                for district, district_votes in allocated.items():
                    node = nodes[(scope, contest)].setdefault(district, {
                        "dem_votes": 0.0,
                        "rep_votes": 0.0,
                        "other_votes": 0.0,
                        "total_votes": 0.0,
                        "dem_candidate": "",
                        "rep_candidate": "",
                    })
                    layers.add_result_votes(node, district_votes, info["party"], info["candidate"])
                    if cd:
                        regular_pools[(scope, contest, column, cd)][district] += district_votes
                        party_pools[(scope, contest, info["party"], cd)][district] += district_votes

    residual_audit = []
    for scope, contest, column, info, cd, votes, row in residuals:
        precinct_label = str(row.get("Precinct") or "")
        is_philadelphia_congressional_residual = (
            row.get("County") == "PHILADELPHIA"
            and (
                "Congressional Mail Votes" in precinct_label
                or re.fullmatch(r"\d+(?:ST|ND|RD|TH) CD", precinct_label, re.IGNORECASE)
            )
            and scope in {"state_house", "state_senate"}
            and cd
        )
        if not is_philadelphia_congressional_residual:
            raise RuntimeError(
                f"Refusing estimated allocation outside Philadelphia mail residuals: "
                f"{scope} {contest} {row.get('County')} {row.get('Precinct')}"
            )
        weights = regular_pools.get((scope, contest, column, cd)) or party_pools.get(
            (scope, contest, info["party"], cd)
        )
        if not weights:
            raise RuntimeError(
                f"No residual allocation pool for {scope} {contest} {column} CD {cd}: "
                f"{row.get('County')} {row.get('Precinct')}"
            )
        allocated = allocate(votes, weights)
        for district, district_votes in allocated.items():
            node = nodes[(scope, contest)].setdefault(district, {
                "dem_votes": 0.0,
                "rep_votes": 0.0,
                "other_votes": 0.0,
                "total_votes": 0.0,
                "dem_candidate": "",
                "rep_candidate": "",
            })
            layers.add_result_votes(node, district_votes, info["party"], info["candidate"])
        method_counts[scope]["congressional_mail_candidate_vote_share"] += 1
        residual_audit.append({
            "scope": scope,
            "contest": contest,
            "column": column,
            "congressional_district": cd,
            "votes": votes,
            "county": row.get("County"),
            "precinct": row.get("Precinct"),
            "district_weights": allocated,
        })

    files = []
    for (scope, contest), results in sorted(nodes.items()):
        round_district_vote_components(results)
        finalized = {}
        for district, node in sorted(results.items(), key=lambda item: int(item[0])):
            layers.finalize_result_node(node)
            finalized[district] = node
        total = sum(node["total_votes"] for node in finalized.values())
        if total != controls[contest]:
            raise RuntimeError(f"{scope} {contest}: {total} != RDH control {controls[contest]}")
        if len(finalized) != EXPECTED[scope]:
            raise RuntimeError(f"{scope} {contest}: observed {len(finalized)} districts")
        filename = f"{scope}_{contest}_{args.year}.json"
        payload = {
            "scope": scope,
            "contest_type": contest,
            "year": args.year,
            "meta": {
                "districts_observed": len(finalized),
                "districts_expected": EXPECTED[scope],
                "coverage_percent": 100.0,
                "source": f"RDH {args.year} precinct matrix with embedded districts and BEF/BAF fallback",
                "allocation_audit": {
                    "source_rows": source_rows[contest],
                    "source_votes": controls[contest],
                    "matched_rows": source_rows[contest],
                    "matched_votes": controls[contest],
                    "unmatched_rows": 0,
                    "unmatched_votes": 0,
                    "unmatched_precincts": [],
                    "unmatched_precinct_votes": {},
                    "mapping_methods": dict(sorted(method_counts[scope].items())),
                    "allocated_rows": source_rows[contest],
                    "allocated_votes": total,
                    "unallocated_rows": 0,
                    "unallocated_votes": 0,
                    "allocation_vote_delta": 0,
                    "conserved_for_matched_rows": True,
                },
            },
            "general": {"results": finalized},
        }
        (args.output / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        files.append({
            "scope": scope,
            "contest_type": contest,
            "year": args.year,
            "file": filename,
            "districts": EXPECTED[scope],
            "rows": len(finalized),
        })

    (args.output / "manifest.json").write_text(
        json.dumps({"scope": "multi", "files": files}, indent=2) + "\n", encoding="utf-8"
    )
    audit = {
        "source": str(source.relative_to(ROOT)),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "rows": len(rows),
        "unique_ids": len(unique_ids),
        "controls": {
            contest: {
                "dem_votes": party_controls[contest]["dem_votes"],
                "rep_votes": party_controls[contest]["rep_votes"],
                "other_votes": party_controls[contest]["other_votes"],
                "total_votes": total,
            }
            for contest, total in sorted(controls.items())
        },
        "mapping_methods": {scope: dict(sorted(counts.items())) for scope, counts in method_counts.items()},
        "unmapped_source_rows": {scope: failures for scope, failures in row_failures.items()},
        "residual_allocations": residual_audit,
    }
    (args.output / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"files": len(files), "controls": audit["controls"], "residuals": len(residual_audit)}, indent=2))


if __name__ == "__main__":
    main()

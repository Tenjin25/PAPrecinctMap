"""Correct Lower Yoder Township rows leaked through a reused Cambria VTD code."""

from __future__ import annotations

import csv
import re
from collections import defaultdict

import build_pa_precinct_returns as build


YEARS = (2022, 2024)
NUMERIC_FIELDS = ("votes", "election_day", "mail", "provisional")
SOURCE_RE = re.compile(r"^LOWER YODER X ([12])(?:\s|$)")

# Existing VTD20 bridge allocation responsible for the leaked District 1 rows.
OLD_DISTRICT_1 = {
    "CAMBRIA - 0211155": 0.160076359249,
    "CAMBRIA - 0211165": 0.054765741725,
    "CAMBRIA - 0211240": 0.000844173286,
    "CAMBRIA - 0211105": 0.078431372549,
    "CAMBRIA - 0211265": 0.039215686275,
    "CAMBRIA - 0211980": 0.019607843137,
    "CAMBRIA - 0211255": 0.647058823529,
}
OLD_DISTRICT_2 = {"CAMBRIA - 0211265": 1.0}

# Current Lower Yoder District 1 is represented by Precincts 01 and 02.
# District 2 is represented by Precinct 03.
CORRECT = {
    1: {"CAMBRIA - 0211240": 453, "CAMBRIA - 0211255": 1022},
    2: {"CAMBRIA - 0211265": 889},
}


def source_district(row: dict[str, str]) -> int | None:
    match = SOURCE_RE.match(build.normalize_token(row.get("precinct")))
    return int(match.group(1)) if match else None


def row_key(row: dict[str, str]) -> tuple[str, ...]:
    # Candidate display names in older generated rows may retain middle names
    # that the shared county-mode label normalizer removes.  Party + contest +
    # exact weighted vote value uniquely identifies these leaked contributions.
    return tuple(
        build.normalize_token(row.get(field))
        for field in ("precinct", "office", "district", "party")
    )


def office_totals(rows: list[dict[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[build.normalize_token(row.get("office"))] += float(row.get("votes") or 0)
    return totals


def repair_year(year: int) -> tuple[int, int]:
    source, _ = build.choose_source(year)
    if source is None:
        raise RuntimeError(f"{year}: official source unavailable")
    source_rows = build.canonical_rows(source, year)
    build.align_candidate_names(source_rows, year)
    selected = [
        row for row in source_rows
        if build.normalize_token(row.get("county")) == "CAMBRIA"
        and source_district(row) in CORRECT
    ]
    if not selected:
        raise RuntimeError(f"{year}: no Lower Yoder source rows")

    target = build.OUTPUT_ROOT / str(year) / build.TARGETS[year]
    with target.open(newline="", encoding="utf-8-sig") as handle:
        existing = list(csv.DictReader(handle))
    indexed: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in existing:
        indexed[row_key(row)].append(row)

    removed_ids: set[int] = set()
    removed: list[dict[str, str]] = []
    for source_row in selected:
        district = source_district(source_row)
        old_weights = OLD_DISTRICT_1 if district == 1 else OLD_DISTRICT_2
        for precinct, weight in old_weights.items():
            lookup = {
                **source_row,
                "precinct": precinct,
            }
            candidates = indexed.get(row_key(lookup), [])
            expected_votes = float(source_row.get("votes") or 0) * weight
            match = next(
                (
                    row for row in candidates
                    if id(row) not in removed_ids
                    and abs(float(row.get("votes") or 0) - expected_votes) < 1e-6
                ),
                None,
            )
            if match is None:
                raise RuntimeError(f"{year}: could not isolate leaked Lower Yoder row {row_key(lookup)}")
            removed_ids.add(id(match))
            removed.append(match)

    replacement: list[dict[str, str]] = []
    for source_row in selected:
        district = source_district(source_row)
        assert district is not None
        populations = CORRECT[district]
        total_population = sum(populations.values())
        for precinct, population in populations.items():
            row = {**source_row, "county": "CAMBRIA", "precinct": precinct}
            row.pop("source_precinct", None)
            weight = population / total_population
            for field in NUMERIC_FIELDS:
                raw = str(source_row.get(field) or "").strip()
                if raw:
                    row[field] = f"{float(raw) * weight:.12f}".rstrip("0").rstrip(".")
            replacement.append(row)

    before = office_totals(removed)
    after = office_totals(replacement)
    if set(before) != set(after) or any(abs(before[key] - after[key]) > 1e-6 for key in before):
        raise RuntimeError(f"{year}: Lower Yoder repair changed office totals")
    output = [row for row in existing if id(row) not in removed_ids] + replacement
    build.write_rows(target, output)
    build.refresh_manifest_output_stats(year, output)
    return len(removed), len(replacement)


if __name__ == "__main__":
    for election_year in YEARS:
        removed_count, replacement_count = repair_year(election_year)
        print(f"{election_year}: replaced {removed_count} leaked rows with {replacement_count} corrected rows")

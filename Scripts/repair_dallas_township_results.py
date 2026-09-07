"""Rejoin Dallas Township Districts 1-5 without rebuilding unrelated precincts."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict

import build_pa_precinct_returns as build


YEARS = (2022, 2024)
MIDDLE_PRECINCT = "LUZERNE - 079200"
SOUTH_PRECINCT = "LUZERNE - 079220"
SOURCE_NAMES = {
    name
    for number in range(1, 6)
    for name in (f"DALLAS D {number}", f"DALLAS DISTRICT {number}")
}


def office_totals(rows: list[dict[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[build.normalize_token(row.get("office"))] += float(row.get("votes") or 0)
    return totals


def repair_year(year: int) -> tuple[int, int]:
    source, _ = build.choose_source(year)
    if source is None:
        raise RuntimeError(f"{year}: official source is unavailable")
    source_rows = build.canonical_rows(source, year)
    build.align_candidate_names(source_rows, year)
    selected = [
        row for row in source_rows
        if build.normalize_token(row.get("county")) == "LUZERNE"
        and any(
            build.normalize_token(row.get("precinct")).startswith(f"{name} ")
            or build.normalize_token(row.get("precinct")) == name
            for name in SOURCE_NAMES
        )
    ]
    if not selected:
        raise RuntimeError(f"{year}: no Dallas Township District 1-5 source rows found")

    # The deployed Middle rows already conserve statewide totals and can carry
    # small upstream adjustments. Split each of those rows using the official
    # District 2-3 versus District 4-5 vote ratio instead of replacing totals.
    source_weights: dict[tuple[str, str, str], list[float]] = defaultdict(
        lambda: [0.0, 0.0]
    )
    for row in selected:
        name = build.normalize_token(row.get("precinct"))
        key = tuple(build.normalize_token(row.get(field)) for field in ("office", "district", "party"))
        bucket = 0 if any(f"DALLAS D {number}" in name for number in (2, 3)) else 1
        if any(f"DALLAS D {number}" in name for number in (2, 3, 4, 5)):
            source_weights[key][bucket] += float(row.get("votes") or 0)

    target = build.OUTPUT_ROOT / str(year) / build.TARGETS[year]
    with target.open(newline="", encoding="utf-8-sig") as handle:
        existing = list(csv.DictReader(handle))
    removed = [row for row in existing if build.normalize_token(row.get("precinct")) == MIDDLE_PRECINCT]
    kept = [
        row for row in existing
        if build.normalize_token(row.get("precinct")) not in {MIDDLE_PRECINCT, SOUTH_PRECINCT}
    ]
    replacement = []
    for row in removed:
        key = tuple(build.normalize_token(row.get(field)) for field in ("office", "district", "party"))
        middle_votes, south_votes = source_weights.get(key, (0.0, 0.0))
        total = middle_votes + south_votes
        if total <= 0:
            raise RuntimeError(f"{year}: no official Dallas split ratio for {key}")
        for precinct, weight in (
            (MIDDLE_PRECINCT, middle_votes / total),
            (SOUTH_PRECINCT, south_votes / total),
        ):
            split_row = {**row, "precinct": precinct}
            for field in ("votes", "election_day", "mail", "provisional"):
                raw = str(row.get(field) or "").strip()
                if raw:
                    split_row[field] = f"{float(raw) * weight:.12f}".rstrip("0").rstrip(".")
            replacement.append(split_row)
    before = office_totals(removed)
    after = office_totals(replacement)
    if set(before) != set(after) or any(abs(before[key] - after[key]) > 1e-6 for key in before):
        raise RuntimeError(f"{year}: Dallas-only repair did not preserve office totals")

    output = kept + replacement
    build.write_rows(target, output)
    build.refresh_manifest_output_stats(year, output)
    return len(removed), len(replacement)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, choices=YEARS, default=list(YEARS))
    args = parser.parse_args()
    for year in sorted(set(args.years)):
        removed, added = repair_year(year)
        print(f"{year}: replaced {removed:,} Dallas Township rows with {added:,} corrected rows")


if __name__ == "__main__":
    main()

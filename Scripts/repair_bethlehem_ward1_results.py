"""Move misallocated Bethlehem Ward 1 returns out of Bethlehem Township."""

from __future__ import annotations

import csv
from collections import defaultdict

import build_pa_precinct_returns as build


YEARS = (2022, 2024)
NORTH = "NORTHAMPTON - 095070"
SOUTH = "NORTHAMPTON - 095080"
WRONG_TOWNSHIP = "NORTHAMPTON - 095330"
POPULATIONS = {NORTH: 1687, SOUTH: 2159}
NUMERIC_FIELDS = ("votes", "election_day", "mail", "provisional")
SIGNATURE_FIELDS = ("office", "district", "party", "candidate", *NUMERIC_FIELDS)


def normalized_signature(row: dict[str, str]) -> tuple[str, ...]:
    return tuple(build.normalize_token(row.get(field)) for field in SIGNATURE_FIELDS)


def office_totals(rows: list[dict[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[build.normalize_token(row.get("office"))] += float(row.get("votes") or 0)
    return totals


def repair_year(year: int) -> tuple[int, int]:
    target = build.OUTPUT_ROOT / str(year) / build.TARGETS[year]
    with target.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))

    north_rows = [row for row in rows if build.normalize_token(row.get("precinct")) == NORTH]
    if not north_rows:
        raise RuntimeError(f"{year}: no Bethlehem Ward 1 North rows")
    if any(build.normalize_token(row.get("precinct")) == SOUTH for row in rows):
        raise RuntimeError(f"{year}: Bethlehem Ward 1 South is already populated")

    township_by_signature: dict[tuple[str, ...], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        if build.normalize_token(row.get("precinct")) == WRONG_TOWNSHIP:
            township_by_signature[normalized_signature(row)].append(row)

    paired: list[tuple[dict[str, str], dict[str, str]]] = []
    removed_ids: set[int] = set()
    for north_row in north_rows:
        candidates = township_by_signature.get(normalized_signature(north_row), [])
        if not candidates:
            raise RuntimeError(f"{year}: missing matching Bethlehem Township contamination row")
        wrong_row = candidates.pop()
        removed_ids.add(id(wrong_row))
        paired.append((north_row, wrong_row))

    removed_ids.update(id(row) for row in north_rows)
    kept = [row for row in rows if id(row) not in removed_ids]
    total_population = sum(POPULATIONS.values())
    replacement: list[dict[str, str]] = []
    for north_row, wrong_row in paired:
        for precinct, population in POPULATIONS.items():
            split_row = {**north_row, "precinct": precinct}
            weight = population / total_population
            for field in NUMERIC_FIELDS:
                values = [str(row.get(field) or "").strip() for row in (north_row, wrong_row)]
                if any(values):
                    total = sum(float(value or 0) for value in values)
                    split_row[field] = f"{total * weight:.12f}".rstrip("0").rstrip(".")
            replacement.append(split_row)

    before = office_totals(rows)
    output = kept + replacement
    after = office_totals(output)
    if set(before) != set(after) or any(abs(before[key] - after[key]) > 1e-6 for key in before):
        raise RuntimeError(f"{year}: Bethlehem repair changed office totals")
    build.write_rows(target, output)
    build.refresh_manifest_output_stats(year, output)
    return len(north_rows), len(replacement)


if __name__ == "__main__":
    for election_year in YEARS:
        removed, added = repair_year(election_year)
        print(f"{election_year}: rebuilt {removed} Ward 1 rows as {added} North/South rows")

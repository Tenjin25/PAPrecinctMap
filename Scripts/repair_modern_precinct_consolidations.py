"""Split consolidated modern returns across current precinct polygons.

This is deliberately a targeted post-processing repair.  The official source
occasionally reports a single modern precinct after several older map pieces
were consolidated.  The current geometry still retains those pieces, so the
reported row is divided by 2020 Census block population without rebuilding or
changing any unrelated precinct.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict

import build_pa_precinct_returns as build


NUMERIC_FIELDS = ("votes", "election_day", "mail", "provisional")

# year: (existing aggregate target, {current target: block population})
SPLITS = {
    2022: (
        # The official Johnstown W8 D3 includes the current ED03 and ED04 pieces.
        ("CAMBRIA - 021880", {"CAMBRIA - 021880": 1080, "CAMBRIA - 021890": 451}),
        ("LANCASTER - 0711200", {"LANCASTER - 0711200": 1321, "LANCASTER - 0711210": 605}),
    ),
    2024: (
        ("CAMBRIA - 021880", {"CAMBRIA - 021880": 1080, "CAMBRIA - 021890": 451}),
        # Meadville Ward 3 Precinct 1 now contains the former W3P2, W4, and W5.
        ("CRAWFORD - 039260", {
            "CRAWFORD - 039260": 1466,
            "CRAWFORD - 039270": 984,
            "CRAWFORD - 039280": 364,
            "CRAWFORD - 039290": 402,
        }),
        # Titusville's seven older pieces are reported as Wards 1, 2, and 3.
        ("CRAWFORD - 039480", {"CRAWFORD - 039470": 818, "CRAWFORD - 039480": 879}),
        ("CRAWFORD - 039490", {"CRAWFORD - 039490": 787, "CRAWFORD - 039500": 1334}),
        ("CRAWFORD - 039510", {
            "CRAWFORD - 039510": 337,
            "CRAWFORD - 039520": 752,
            "CRAWFORD - 039530": 355,
        }),
        ("LANCASTER - 0711200", {"LANCASTER - 0711200": 1321, "LANCASTER - 0711210": 605}),
        # These official rows dropped the older sub-precinct suffix in 2024.
        ("DAUPHIN - 043880", {"DAUPHIN - 043870": 1613, "DAUPHIN - 043880": 2238}),
        ("PIKE - 103070", {"PIKE - 103070": 1364, "PIKE - 103080": 998}),
        ("WESTMORELAND - 1292230", {
            "WESTMORELAND - 1292230": 2853,
            "WESTMORELAND - 1292240": 139,
        }),
    ),
}


def office_totals(rows: list[dict[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[build.normalize_token(row.get("office"))] += float(row.get("votes") or 0)
    return totals


def split_rows(rows: list[dict[str, str]], source: str, populations: dict[str, int]) -> list[dict[str, str]]:
    selected = [row for row in rows if build.normalize_token(row.get("precinct")) == source]
    if not selected:
        raise RuntimeError(f"No rows found for consolidated precinct {source}")
    targets = {build.normalize_token(value) for value in populations}
    occupied = {
        build.normalize_token(row.get("precinct"))
        for row in rows
        if build.normalize_token(row.get("precinct")) in targets
        and build.normalize_token(row.get("precinct")) != source
    }
    if occupied:
        raise RuntimeError(f"Refusing to overwrite populated targets: {sorted(occupied)}")

    total_population = sum(populations.values())
    replacement: list[dict[str, str]] = []
    for row in selected:
        for target, population in populations.items():
            weight = population / total_population
            split_row = {**row, "precinct": target}
            for field in NUMERIC_FIELDS:
                raw = str(row.get(field) or "").strip()
                if raw:
                    split_row[field] = f"{float(raw) * weight:.12f}".rstrip("0").rstrip(".")
            replacement.append(split_row)
    return [row for row in rows if build.normalize_token(row.get("precinct")) != source] + replacement


def repair_year(year: int) -> tuple[int, int]:
    target = build.OUTPUT_ROOT / str(year) / build.TARGETS[year]
    with target.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    before = office_totals(rows)
    original_count = len(rows)
    for source, populations in SPLITS[year]:
        rows = split_rows(rows, source, populations)
    after = office_totals(rows)
    if set(before) != set(after) or any(abs(before[key] - after[key]) > 1e-6 for key in before):
        raise RuntimeError(f"{year}: consolidation repair changed office totals")
    build.write_rows(target, rows)
    build.refresh_manifest_output_stats(year, rows)
    return original_count, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, choices=sorted(SPLITS), default=sorted(SPLITS))
    args = parser.parse_args()
    for year in sorted(set(args.years)):
        before, after = repair_year(year)
        print(f"{year}: {before:,} rows -> {after:,} rows; office totals preserved")


if __name__ == "__main__":
    main()

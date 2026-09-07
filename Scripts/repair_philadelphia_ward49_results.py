"""Rebuild Philadelphia Ward 49 on current polygons with a Census-block overlay.

The Pennsylvania geometry retains 25 older fragments, while Philadelphia's
official 2022/2024 election geography has 22 divisions.  The weights below are
2020 Census block populations assigned by representative point to both the
City Commissioners' current Political Divisions layer and the app geometry.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict

import build_pa_precinct_returns as build


YEARS = (2022, 2024)
NUMERIC_FIELDS = ("votes", "election_day", "mail", "provisional")
WARD49_RE = re.compile(r"^PHILADELPHIA W(?:ARD)? 49 P(?:RECINCT)? ?0?(\d+)(?:\s|$)")
CURRENT_RE = re.compile(r"^PHILADELPHIA - 10149\d{2}$")

# Official division -> {current polygon: Census block population}.
BLOCK_POPULATIONS = {
    1: {"1014901": 1032, "1014913": 20},
    2: {"1014921": 31, "1014923": 1011},
    3: {"1014924": 1557},
    4: {"1014904": 724},
    5: {"1014905": 1093},
    6: {"1014925": 773},
    7: {"1014907": 1061},
    8: {"1014908": 1060},
    9: {"1014909": 2043},
    10: {"1014910": 1073},
    11: {"1014911": 1320},
    12: {"1014911": 52, "1014912": 1138},
    13: {"1014902": 193, "1014913": 552},
    14: {"1014902": 52, "1014914": 775},
    15: {"1014906": 26, "1014915": 915},
    16: {"1014916": 896},
    17: {"1014917": 1079},
    18: {"1014908": 77, "1014918": 513, "1014925": 357},
    19: {"1014910": 162, "1014914": 188, "1014919": 607},
    20: {"1014920": 928},
    21: {"1014921": 1347},
    22: {"1014922": 1292},
}


def office_totals(rows: list[dict[str, str]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for row in rows:
        totals[build.normalize_token(row.get("office"))] += float(row.get("votes") or 0)
    return totals


def source_division(row: dict[str, str]) -> int | None:
    match = WARD49_RE.match(build.normalize_token(row.get("precinct")))
    return int(match.group(1)) if match else None


def repair_year(year: int) -> tuple[int, int]:
    source, _ = build.choose_source(year)
    if source is None:
        raise RuntimeError(f"{year}: official source unavailable")
    source_rows = build.canonical_rows(source, year)
    build.align_candidate_names(source_rows, year)
    selected = [
        row for row in source_rows
        if build.normalize_token(row.get("county")) == "PHILADELPHIA"
        and source_division(row) in BLOCK_POPULATIONS
    ]
    if not selected:
        raise RuntimeError(f"{year}: no official Philadelphia Ward 49 rows")

    target = build.OUTPUT_ROOT / str(year) / build.TARGETS[year]
    with target.open(newline="", encoding="utf-8-sig") as handle:
        existing = list(csv.DictReader(handle))
    removed = [row for row in existing if CURRENT_RE.match(build.normalize_token(row.get("precinct")))]
    kept = [row for row in existing if not CURRENT_RE.match(build.normalize_token(row.get("precinct")))]

    replacement: list[dict[str, str]] = []
    for row in selected:
        division = source_division(row)
        assert division is not None
        populations = BLOCK_POPULATIONS[division]
        total_population = sum(populations.values())
        for code, population in populations.items():
            split_row = {**row, "county": "PHILADELPHIA", "precinct": f"PHILADELPHIA - {code}"}
            split_row.pop("source_precinct", None)
            weight = population / total_population
            for field in NUMERIC_FIELDS:
                raw = str(row.get(field) or "").strip()
                if raw:
                    split_row[field] = f"{float(raw) * weight:.12f}".rstrip("0").rstrip(".")
            replacement.append(split_row)

    before = office_totals(removed)
    after = office_totals(replacement)
    if set(before) != set(after) or any(abs(before[key] - after[key]) > 1e-6 for key in before):
        differences = {key: after.get(key, 0) - value for key, value in before.items()}
        raise RuntimeError(f"{year}: Ward 49 office totals differ: {differences}")
    output = kept + replacement
    build.write_rows(target, output)
    build.refresh_manifest_output_stats(year, output)
    return len(removed), len(replacement)


if __name__ == "__main__":
    for election_year in YEARS:
        removed_count, replacement_count = repair_year(election_year)
        print(f"{election_year}: replaced {removed_count} Ward 49 rows with {replacement_count} block-weighted rows")

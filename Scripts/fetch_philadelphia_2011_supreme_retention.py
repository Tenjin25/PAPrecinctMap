#!/usr/bin/env python3
"""Extract Philadelphia's certified 2011 Supreme Court retention precinct data.

The statewide PA bulk precinct export omits this contest for Philadelphia.  The
City Commissioners publish the certified ward-and-division results as a CSV;
this script preserves a small, normalized supplemental extract for the atlas.
"""

from __future__ import annotations

import csv
import io
import urllib.request
from collections import Counter
from pathlib import Path


SOURCE_URL = 'https://files7.philadelphiavotes.com/election-results/2011_GENERAL.csv'
OUTPUT = Path('data/Openelections/2011/supplemental/philadelphia_2011_supreme_retention.csv')
EXPECTED_TOTALS = {'Yes': 74166, 'No': 21630}


def precinct_label(ward: str, division: str) -> str:
    # Matches the Philadelphia identifiers used by PA's 2011 precinct export:
    # ward 1, division 1 => PHILADELPHIA - 101101.
    return f'PHILADELPHIA - 101{int(ward)}{int(division):02d}'


def main() -> None:
    with urllib.request.urlopen(SOURCE_URL) as response:
        content = response.read().decode('utf-8-sig')

    totals: Counter[str] = Counter()
    rows = []
    for row in csv.DictReader(io.StringIO(content)):
        if row.get('OFFICE', '').strip().upper() != 'JUSTICE OF THE SUPREME COURT':
            continue
        name = row.get('NAME', '').strip().upper()
        choice = 'Yes' if name == 'EAKIN YES SI' else 'No' if name == 'EAKIN NO NO' else ''
        if not choice:
            continue
        votes = int(row.get('VOTES') or 0)
        totals[choice] += votes
        rows.append({
            'county': 'PHILADELPHIA',
            'precinct': precinct_label(row['WARD'], row['DIVISION']),
            'office': 'Supreme Court Retention - J Michael Eakin',
            'district': '',
            'party': choice.upper(),
            'candidate': choice,
            'votes': votes,
            'election_day': '',
            'mail': '',
            'provisional': '',
        })

    if dict(totals) != EXPECTED_TOTALS:
        raise SystemExit(f'Philadelphia county-total validation failed: {dict(totals)}')

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows):,} certified precinct rows to {OUTPUT}.')
    print(f'Validated Philadelphia totals: Yes {totals["Yes"]:,}; No {totals["No"]:,}.')


if __name__ == '__main__':
    main()

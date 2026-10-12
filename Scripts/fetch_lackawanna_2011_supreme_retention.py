#!/usr/bin/env python3
"""Extract certified Lackawanna County 2011 Eakin retention precinct returns."""

from __future__ import annotations

import csv
import html
import re
import urllib.request
from pathlib import Path


SOURCE_URL = 'https://ww2.lackawannacounty.org/election%20results/110811/EL30.HTM'
OUTPUT = Path('data/Openelections/2011/supplemental/lackawanna_2011_supreme_retention.csv')
EXPECTED_TOTALS = (24798, 9524)


def report_text(source: str) -> str:
    return html.unescape(re.sub(r'<[^>]+>', '', source))


def main() -> None:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={'User-Agent': 'Mozilla/5.0 (compatible; PAPrecinctMap/1.0)'},
    )
    with urllib.request.urlopen(request) as response:
        text = report_text(response.read().decode('latin1'))

    rows = []
    for block in re.split(r'(?=^\s{10}\d{4}\s)', text, flags=re.M):
        header = re.match(r'\s*(\d{4}\s+[^\n]+)', block)
        if not header or 'RETAIN J. MICHAEL EAKIN' not in block:
            continue
        section = block[block.find('RETAIN J. MICHAEL EAKIN'):]
        section = section.split('JUDGE OF THE SUPERIOR COURT', 1)[0]
        yes = re.search(r'\n\s*Yes\s+\.(?:\s*\.)*\s+(\d+)', section)
        no = re.search(r'\n\s*No\.?(?:\s*\.)*\s+(\d+)', section)
        if not (yes and no):
            raise SystemExit(f'Could not parse Eakin votes for {header.group(1).strip()}')
        precinct = header.group(1).strip()
        for choice, match in (('YES', yes), ('NO', no)):
            rows.append({
                'county': 'LACKAWANNA',
                'precinct': precinct,
                'office': 'Supreme Court Retention - J Michael Eakin',
                'district': '',
                'party': choice,
                'candidate': choice.title(),
                'votes': int(match.group(1)),
                'election_day': '',
                'mail': '',
                'provisional': '',
            })

    totals = (
        sum(row['votes'] for row in rows if row['party'] == 'YES'),
        sum(row['votes'] for row in rows if row['party'] == 'NO'),
    )
    if totals != EXPECTED_TOTALS:
        raise SystemExit(f'Lackawanna county-total validation failed: {totals}')

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows):,} certified precinct rows to {OUTPUT}.')
    print(f'Validated Lackawanna totals: Yes {totals[0]:,}; No {totals[1]:,}.')


if __name__ == '__main__':
    main()

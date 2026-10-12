#!/usr/bin/env python3
"""Extract official Montour County 2011 Eakin retention precinct returns."""

from __future__ import annotations

import csv
import io
import re
import urllib.request
from pathlib import Path

from pypdf import PdfReader


SOURCE_URL = 'https://www.montourcounty.gov/getmedia/64c7874f-c45d-4310-b515-46396bc430af/Results11811.pdf'
OUTPUT = Path('data/Openelections/2011/supplemental/montour_2011_supreme_retention.csv')
EXPECTED_TOTALS = (1732, 635)


def main() -> None:
    request = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0 (compatible; PAPrecinctMap/1.0)'})
    with urllib.request.urlopen(request) as response:
        reader = PdfReader(io.BytesIO(response.read()))

    text = next(
        (page.extract_text() or '')
        for page in reader.pages
        if 'Michael Eakin' in (page.extract_text() or '')
    )
    table = text[text.index('15 PRECINCTS'):text.index('GRAND TOTALS')]
    rows = []
    for line in table.splitlines():
        match = re.match(r'^(\d{4}\s+.*?)(?=\s+[ ,I]*\s*\d+\s+\d+\s+\d+\.\d+)', line)
        if not match:
            continue
        precinct = match.group(1)
        numbers = re.findall(r'\d+(?:\.\d+)?', line)[1:]
        if len(numbers) < 5:
            continue
        yes, no = numbers[3:5]
        for choice, votes in (('YES', yes), ('NO', no)):
            rows.append({
                'county': 'MONTOUR', 'precinct': precinct.strip(),
                'office': 'Supreme Court Retention - J Michael Eakin', 'district': '',
                'party': choice, 'candidate': choice.title(), 'votes': int(votes),
                'election_day': '', 'mail': '', 'provisional': '',
            })

    totals = (sum(r['votes'] for r in rows if r['party'] == 'YES'), sum(r['votes'] for r in rows if r['party'] == 'NO'))
    if len(rows) != 30 or totals != EXPECTED_TOTALS:
        raise SystemExit(f'Montour extraction validation failed: rows={len(rows)}, totals={totals}')

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f'Wrote {len(rows)} certified precinct rows to {OUTPUT}.')
    print(f'Validated Montour totals: Yes {totals[0]:,}; No {totals[1]:,}.')


if __name__ == '__main__':
    main()

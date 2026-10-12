"""Extract all appellate retention votes from Montour's county-published PDF."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://www.montourcounty.gov/getmedia/64c7874f-c45d-4310-b515-46396bc430af/Results11811.pdf'
# County report row IDs are stable across its two retention tables.
NAMES = ['ANTHONY TOWNSHIP', 'COOPER TOWNSHIP', 'DANVILLE BOROUGH FIRST',
         'DANVILLE BOROUGH SECOND', 'DANVILLE BOROUGH THIRD', 'DANVILLE BOROUGH FOURTH',
         'DERRY TOWNSHIP', 'LIBERTY TOWNSHIP', 'LIMESTONE TOWNSHIP', 'MAHONING I',
         'MAHONING II', 'MAYBERRY TOWNSHIP', 'VALLEY TOWNSHIP',
         'WASHINGTONVILLE BOROUGH', 'WEST HEMLOCK TOWNSHIP']
GROUPS = [
    ('Michael Eakin', [('J. Michael Eakin', 'Supreme Court'), ('John T. Bender', 'Superior Court'),
                       ('Mary Jane Bowes', 'Superior Court'), ('Renee Cohn Jubelirer', 'Commonwealth Court')]),
    ('Retain Mary Hannah Leavitt', [('Mary Hannah Leavitt', 'Commonwealth Court'), ('Robin Simpson', 'Commonwealth Court')]),
]


def recover(source):
    pages = [p.extract_text() or '' for p in PdfReader(source).pages]
    controls = {r['candidate']: (r['yes_votes'], r['no_votes'])
                for r in json.loads((ROOT/'data/pa_historical_judicial_county_results.json').read_text())['elections']['2011']['rows']
                if r['county'] == 'MONTOUR' and r['is_retention']}
    rows, totals = [], {}
    for marker, contests in GROUPS:
        matches = [p for p in pages if marker in p]
        if len(matches) != 1:
            raise ValueError(f'Expected one table for {marker}')
        seen = set()
        for line in matches[0].splitlines():
            match = re.match(r'^(\d{4})\s', line)
            if not match:
                continue
            row_id = int(match[1])
            if row_id in seen or not 1 <= row_id <= 15:
                raise ValueError('Invalid or duplicate precinct')
            seen.add(row_id)
            numbers = re.findall(r'\d+(?:\.\d+)?', line)[1:]
            if len(numbers) != 3 + 2 * len(contests):
                raise ValueError(f'Unexpected columns: {line}')
            for i, (judge, court) in enumerate(contests):
                for j, choice in enumerate(('Yes', 'No')):
                    count = int(numbers[3+2*i+j])
                    totals.setdefault(judge, [0, 0])[j] += count
                    rows.append(dict(county='MONTOUR', precinct=NAMES[row_id-1],
                                     office=f'{court} Retention - {judge}', district='', party=choice.upper(),
                                     candidate=choice, votes=count, election_day='', mail='', provisional=''))
        if len(seen) != 15:
            raise ValueError('Missing precincts')
    for judge, total in totals.items():
        if tuple(total) != controls[judge]:
            raise ValueError(f'County total mismatch for {judge}')
    output = ROOT/'data/Openelections/2011/supplemental/montour_2011_all_retention.csv'
    with output.open('w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    audit = dict(source_url=SOURCE_URL, source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                 source_status='County-published election-night canvass; totals match final state county returns',
                 row_count=len(rows), precinct_count=15, county_totals=totals,
                 normalization='Expanded truncated municipality names and preserved Mahoning I/II by report row ID')
    output.with_suffix('.source.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    recover(parser.parse_args().source)

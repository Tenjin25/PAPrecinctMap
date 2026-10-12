"""Recover the five remaining appellate retention questions from certified HTML."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

from fetch_lackawanna_2011_supreme_retention import SOURCE_URL, report_text

ROOT = Path(__file__).resolve().parents[1]
CONTESTS = {
    'John T. Bender': 'Superior Court',
    'Mary Jane Bowes': 'Superior Court',
    'Renee Cohn Jubelirer': 'Commonwealth Court',
    'Mary Hannah Leavitt': 'Commonwealth Court',
    'Robin Simpson': 'Commonwealth Court',
}


def recover(source):
    raw = source.read_bytes()
    text = report_text(raw.decode('latin1'))
    if 'CERTIFIED' not in text or 'NOVEMBER 8, 2011' not in text:
        raise ValueError('Expected certified November 8, 2011 report')
    county_data = json.loads((ROOT / 'data/pa_historical_judicial_county_results.json').read_text())
    controls = {r['candidate']: (r['yes_votes'], r['no_votes'])
                for r in county_data['elections']['2011']['rows']
                if r['county'] == 'LACKAWANNA' and r['is_retention']}
    rows, seen = [], set()
    totals = {name: [0, 0] for name in CONTESTS}
    for block in re.split(r'(?=^\s{10}\d{4}\s)', text, flags=re.M):
        header = re.match(r'\s*(\d{4})\s+([^\n]+)', block)
        if not header:
            continue
        precinct_id, precinct_name = header.groups()
        if precinct_id in seen:
            raise ValueError(f'Duplicate precinct {precinct_id}')
        seen.add(precinct_id)
        for name, court in CONTESTS.items():
            marker = 'RETAIN ' + name.upper()
            if marker not in block:
                raise ValueError(f'Missing {name} in {precinct_id}')
            section = block.split(marker, 1)[1].split('Total', 1)[0]
            for index, choice in enumerate(('Yes', 'No')):
                match = re.search(r'\n\s*' + choice + r'[ .]+(\d+)\b', section)
                if not match:
                    raise ValueError(f'Missing {choice} for {name} in {precinct_id}')
                votes = int(match.group(1))
                totals[name][index] += votes
                rows.append(dict(county='LACKAWANNA', precinct=f'{precinct_id} {precinct_name.strip()}',
                                 office=f'{court} Retention - {name}', district='', party=choice.upper(),
                                 candidate=choice, votes=votes, election_day='', mail='', provisional=''))
    if len(seen) != 163:
        raise ValueError(f'Expected 163 precincts, found {len(seen)}')
    for name, total in totals.items():
        if tuple(total) != controls[name]:
            raise ValueError(f'{name}: {total} differs from official county total {controls[name]}')
    output = ROOT / 'data/Openelections/2011/supplemental/lackawanna_2011_other_retention.csv'
    with output.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audit = dict(source_url=SOURCE_URL, source_sha256=hashlib.sha256(raw).hexdigest(),
                 precinct_count=len(seen), row_count=len(rows), county_totals=totals,
                 validation='All five Yes/No totals exactly match official state county returns',
                 geography_status='Original county precinct labels preserved; district matching not validated')
    output.with_suffix('.source.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Downloaded official EL30.HTM report')
    recover(parser.parse_args().source)

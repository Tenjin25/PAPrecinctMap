"""Recover remaining appellate retentions from Philadelphia's certified CSV."""
import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

from fetch_philadelphia_2011_supreme_retention import SOURCE_URL, precinct_label

ROOT = Path(__file__).resolve().parents[1]
CONTESTS = {
    'BENDER': ('John T. Bender', 'Superior Court'),
    'BOWES': ('Mary Jane Bowes', 'Superior Court'),
    'COHN JUBELIRER': ('Renee Cohn Jubelirer', 'Commonwealth Court'),
    'LEAVITT': ('Mary Hannah Leavitt', 'Commonwealth Court'),
    'SIMPSON JR': ('Robin Simpson', 'Commonwealth Court'),
}


def recover(source):
    votes = Counter()
    with source.open(encoding='utf-8-sig', newline='') as stream:
        for row in csv.DictReader(stream):
            name = row['NAME'].strip().upper()
            for suffix, choice in ((' YES SI', 'Yes'), (' NO NO', 'No')):
                if not name.endswith(suffix) or name[:-len(suffix)] not in CONTESTS:
                    continue
                judge, court = CONTESTS[name[:-len(suffix)]]
                if row['OFFICE'].strip().upper() != 'JUDGE OF THE ' + court.upper():
                    raise ValueError(f'Unexpected office for {name}')
                count = int(row['VOTES'])
                if count < 0:
                    raise ValueError('Negative vote count')
                votes[(int(row['WARD']), int(row['DIVISION']), judge, court, choice)] += count
    source_data = json.loads((ROOT / 'data/pa_historical_judicial_county_results.json').read_text())
    controls = {r['candidate']: (r['yes_votes'], r['no_votes'])
                for r in source_data['elections']['2011']['rows']
                if r['county'] == 'PHILADELPHIA' and r['is_retention']}
    totals, precincts, rows = {}, {}, []
    for (ward, division, judge, court, choice), count in sorted(votes.items()):
        totals.setdefault(judge, [0, 0])[0 if choice == 'Yes' else 1] += count
        precincts.setdefault(judge, set()).add((ward, division))
        if (ward, division, judge, court, 'No' if choice == 'Yes' else 'Yes') not in votes:
            raise ValueError('Missing Yes/No pair')
        rows.append(dict(county='PHILADELPHIA', precinct=precinct_label(str(ward), str(division)),
                         office=f'{court} Retention - {judge}', district='', party=choice.upper(),
                         candidate=choice, votes=count, election_day='', mail='', provisional=''))
    if set(totals) != {v[0] for v in CONTESTS.values()}:
        raise ValueError('Missing contest')
    for judge, total in totals.items():
        if tuple(total) != controls[judge]:
            raise ValueError(f'{judge}: {total} differs from {controls[judge]}')
    if len({frozenset(p) for p in precincts.values()}) != 1:
        raise ValueError('Precinct coverage differs between questions')
    output = ROOT / 'data/Openelections/2011/supplemental/philadelphia_2011_other_retention.csv'
    with output.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with source.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    audit = dict(source_url=SOURCE_URL, source_sha256=digest, row_count=len(rows),
                 precinct_counts={k: len(v) for k, v in precincts.items()}, county_totals=totals,
                 validation='All five Yes/No totals exactly match official state county returns',
                 aggregation='Machine and ballot-type records summed once per ward/division and choice',
                 geography_status='Existing Philadelphia identifier convention; spatial matching not validated')
    output.with_suffix('.source.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Downloaded official 2011_GENERAL.csv')
    recover(parser.parse_args().source)

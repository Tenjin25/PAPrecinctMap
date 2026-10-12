"""Extract 2011 appellate retention returns from Huntingdon's official precinct PDF."""
import argparse
import csv
import hashlib
import json
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = 'https://www.huntingdoncountypa.gov/getmedia/666f1f82-ee98-4844-a1f2-bf5aa1e46f14/2011-General-Precinct-Official-results.pdf'
SUMMARY_URL = 'https://www.huntingdoncountypa.gov/getmedia/d5aa0b0e-165d-4302-844b-ac3ecb48caac/2011-General-County-Official-results.pdf'
CONTESTS = {
    'J. MICHAEL EAKIN': ('J. Michael Eakin', 'Supreme Court'),
    'JOHN T. BENDER': ('John T. Bender', 'Superior Court'),
    'MARY JANE BOWES': ('Mary Jane Bowes', 'Superior Court'),
    'RENEE COHN JUBELIRER': ('Renee Cohn Jubelirer', 'Commonwealth Court'),
    'MARY HANNAH LEAVITT': ('Mary Hannah Leavitt', 'Commonwealth Court'),
    'ROBIN SIMPSON': ('Robin Simpson', 'Commonwealth Court'),
}


def recover(source, summary):
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(source).pages)
    reports = re.split(r'PRECINCT REPORT\s+HUNTINGDON COUNTY, PENNSYLVANI\s*', text)[1:]
    if len(reports) != 58:
        raise ValueError(f'Expected 58 precinct reports; found {len(reports)}')
    rows, totals, precincts = [], defaultdict(lambda: [0, 0]), set()
    for report in reports:
        match = re.search(r'(?m)^\s*(\d{4})\s+([A-Z][^\n]+)$', report)
        if not match:
            raise ValueError('Missing precinct heading')
        precinct = match[1]+' '+match[2].strip()
        if precinct in precincts:
            raise ValueError(f'Duplicate precinct {precinct}')
        precincts.add(precinct)
        for source_name, (judge, court) in CONTESTS.items():
            sections = re.findall(r'(?m)^\s*RETAIN '+re.escape(source_name)+r'\s*$(.*?)(?=\n\s*(?:RETAIN |PRECINCT REPORT)|\Z)',
                                  report, re.S)
            if len(sections) != 1:
                raise ValueError(f'{precinct}: expected one question for {judge}; found {len(sections)}')
            section = sections[0]
            for i, choice in enumerate(('YES', 'NO')):
                found = re.search(r'(?m)^\s*'+choice+r'\s*(?:\.\s*)+([\d,]+)\s', section)
                if not found:
                    raise ValueError(f'{precinct}: missing {choice} for {judge}')
                votes = int(found[1].replace(',', ''))
                totals[judge][i] += votes
                rows.append(dict(county='HUNTINGDON', precinct=precinct,
                    office=f'{court} Retention - {judge}', district='',
                    party=choice, candidate=choice.title(), votes=votes,
                    election_day='', mail='', provisional=''))
    controls = {r['candidate']: (r['yes_votes'], r['no_votes'])
                for r in json.loads((ROOT / 'data/pa_historical_judicial_county_results.json').read_text())['elections']['2011']['rows']
                if r['county'] == 'HUNTINGDON' and r['is_retention']}
    summary_text = '\n'.join(page.extract_text() or '' for page in PdfReader(summary).pages)
    summary_totals = {}
    for source_name, (judge, _) in CONTESTS.items():
        sections = re.findall(r'(?m)^\s*RETAIN '+re.escape(source_name)+r'\s*$(.*?)(?=\n\s*RETAIN |\Z)',
                              summary_text, re.S)
        if len(sections) != 1:
            raise ValueError(f'Summary missing {judge}')
        counts = []
        for choice in ('YES', 'NO'):
            found = re.search(r'(?m)^\s*'+choice+r'\s*(?:\.\s*)+([\d,]+)\s', sections[0])
            if not found:
                raise ValueError(f'Summary missing {judge} {choice}')
            counts.append(int(found[1].replace(',', '')))
        summary_totals[judge] = counts
        if totals[judge] != counts:
            raise ValueError(f'Precinct report does not match county summary: {judge}')
    reconciliation = {judge: {'precinct': count, 'county_summary': summary_totals[judge],
                              'state_county': controls[judge],
                              'difference': [a-b for a, b in zip(count, controls[judge])]}
                      for judge, count in totals.items()}
    if any(tuple(count) != controls[judge] for judge, count in totals.items()):
        output = ROOT / 'data/historical_sources/huntingdon_2011_retention_reconciliation.json'
        quarantine_csv = output.with_name('huntingdon_2011_retention_unreconciled.csv')
        with quarantine_csv.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        audit = {'status': 'withheld_pending_reconciliation', 'precinct_source_url': SOURCE_URL,
                 'county_summary_url': SUMMARY_URL,
                 'precinct_source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                 'summary_sha256': hashlib.sha256(summary.read_bytes()).hexdigest(),
                 'precinct_count': len(precincts), 'row_count': len(rows),
                 'source_note': 'The county precinct sums match its published official summary; both differ from state county returns.',
                 'extracted_csv': quarantine_csv.name, 'reconciliation': reconciliation}
        output.write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
        print(json.dumps(audit, indent=2))
        return
    output = ROOT / 'data/Openelections/2011/supplemental/huntingdon_2011_all_retention.csv'
    with output.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audit = {'source_url': SOURCE_URL, 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
             'source_status': 'County-published official precinct report, printed 2011-11-15',
             'precinct_count': len(precincts), 'row_count': len(rows),
             'reconciliation': reconciliation}
    output.with_suffix('.source.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('summary', type=Path)
    args = parser.parse_args()
    recover(args.source, args.summary)

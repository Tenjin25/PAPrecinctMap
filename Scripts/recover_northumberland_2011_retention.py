"""Fetch linked official 2011 precinct reports and reconcile appellate retentions."""
import csv
import hashlib
import html
import json
import re
import tempfile
from io import BytesIO
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]
INDEX = 'https://northumberlandcountypa.gov/2011-results/'
CACHE = Path(tempfile.gettempdir()) / 'pa_northumberland_2011'
# The index incorrectly links countywide.pdfm. The published PDF uses .pdf.
SUMMARY_URL = 'https://northumberlandcountypa.gov/htdocs/wp-content/uploads/documents/elections/2011municipalofficial/countywide.pdf'
CONTESTS = {'Eakin': ('J. Michael Eakin', 'Supreme Court'),
            'Bender': ('John T. Bender', 'Superior Court'),
            'Bowes': ('Mary Jane Bowes', 'Superior Court'),
            'Jubelirer': ('Renee Cohn Jubelirer', 'Commonwealth Court'),
            'Leavitt': ('Mary Hannah Leavitt', 'Commonwealth Court'),
            'Simpson': ('Robin Simpson', 'Commonwealth Court')}


def fetch(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.html')
    if cached.exists():
        return cached.read_bytes()
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
    cached.write_bytes(raw)
    return raw


def parse(url):
    raw = fetch(url)
    text = raw.decode('latin1')
    header = re.search(r'Summary For (.*?), All Counters, All Races', text)
    if not header or 'November 8, 2011' not in text:
        raise ValueError(f'Unexpected report: {url}')
    precinct = html.unescape(header[1]).strip()
    rows = []
    for short, (judge, court) in CONTESTS.items():
        sections = re.split(r'<th[^>]*>Retention '+short+r'</th>', text, flags=re.I)
        if len(sections) != 2:
            raise ValueError(f'Missing/duplicate {judge}: {url}')
        section = sections[1].split('</table>', 1)[0]
        for choice in ('YES', 'NO'):
            match = re.search(r'<td[^>]*>'+choice+r'</td>\s*<td[^>]*>\s*</td>\s*<td[^>]*>([\d,]+)</td>', section, re.I)
            if not match:
                raise ValueError(f'Missing {choice}: {url}')
            rows.append(dict(county='NORTHUMBERLAND', precinct=precinct,
                             office=f'{court} Retention - {judge}', district='', party=choice,
                             candidate=choice.title(), votes=int(match[1].replace(',', '')),
                             election_day='', mail='', provisional=''))
    return rows, dict(url=url, sha256=hashlib.sha256(raw).hexdigest(), precinct=precinct)


def summary_totals():
    from pypdf import PdfReader
    raw = fetch(SUMMARY_URL)
    text = '\n'.join(page.extract_text() or '' for page in PdfReader(BytesIO(raw)).pages)
    totals = {}
    for short, (judge, _) in CONTESTS.items():
        section = re.search(r'Retention '+short+r'\b(.*?)(?=Retention |\Z)', text, re.S)
        if not section:
            raise ValueError(f'Missing county summary for {judge}')
        totals[judge] = []
        for choice in ('YES', 'NO'):
            match = re.search(r'\b'+choice+r'\s+([\d,]+)\s', section[1])
            if not match:
                raise ValueError(f'Missing county summary {judge} {choice}')
            totals[judge].append(int(match[1].replace(',', '')))
    return totals, hashlib.sha256(raw).hexdigest()


def main():
    index = fetch(INDEX).decode('utf-8')
    urls = sorted({urljoin(INDEX, html.unescape(u)) for u in re.findall(r'href=[\"\']([^\"\']+)', index)
                   if '2011municipalofficial/votecenter-' in u})
    if not urls:
        raise ValueError('No official precinct links')
    print(f'Fetching {len(urls)} linked precinct reports', flush=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(parse, urls))
    rows = [r for group, _ in results for r in group]
    sources = [s for _, s in results]
    if len({s['precinct'] for s in sources}) != len(sources):
        raise ValueError('Duplicate precincts')
    controls = {r['candidate']: (r['yes_votes'], r['no_votes'])
                for r in json.loads((ROOT/'data/pa_historical_judicial_county_results.json').read_text())['elections']['2011']['rows']
                if r['county']=='NORTHUMBERLAND' and r['is_retention']}
    totals = {}
    reconciliation = {}
    county_summary, summary_sha256 = summary_totals()
    for judge, court in CONTESTS.values():
        totals[judge] = [sum(r['votes'] for r in rows if r['office']==f'{court} Retention - {judge}' and r['party']==choice)
                         for choice in ('YES', 'NO')]
        reconciliation[judge] = {
            'precinct_totals': dict(zip(('yes', 'no'), totals[judge])),
            'county_summary_totals': dict(zip(('yes', 'no'), county_summary[judge])),
            'matches_county_summary': totals[judge] == county_summary[judge],
            'state_county_totals': dict(zip(('yes', 'no'), controls[judge])),
            'precinct_minus_state': dict(zip(('yes', 'no'),
                [a-b for a, b in zip(totals[judge], controls[judge])])),
        }
    mismatched = any(tuple(totals[judge]) != controls[judge] for judge in totals)
    if mismatched:
        audit_path = ROOT / 'data/historical_sources/northumberland_2011_retention_reconciliation.json'
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        quarantine_csv = audit_path.with_name('northumberland_2011_retention_unreconciled.csv')
        with quarantine_csv.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        audit = dict(index_url=INDEX, precinct_count=len(sources), row_count=len(rows),
                     status='withheld_pending_reconciliation', reconciliation=reconciliation,
                     county_summary_url=SUMMARY_URL, county_summary_sha256=summary_sha256,
                     county_report_date='2011-11-22',
                     extracted_csv=quarantine_csv.name,
                     note='Unreconciled CSV is held outside map inputs. Differences are not allocated to precincts.',
                     sources=sources)
        precinct_results = {}
        for row in rows:
            judge = row['office'].split(' Retention - ', 1)[1]
            precinct_results.setdefault(row['precinct'], {}).setdefault(judge, {})[row['party'].lower()] = row['votes']
        extracted_path = audit_path.with_name('northumberland_2011_retention_extracted.json')
        extracted_path.write_text(json.dumps(dict(status=audit['status'],
            reconciliation_file=audit_path.name, precincts=precinct_results), indent=2)+'\n', encoding='utf-8')
        audit_path.write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in audit.items() if k != 'sources'}, indent=2))
        raise SystemExit(1)
    output=ROOT/'data/Openelections/2011/supplemental/northumberland_2011_all_retention.csv'
    with output.open('w', newline='', encoding='utf-8') as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    audit=dict(index_url=INDEX, precinct_count=len(sources), row_count=len(rows), county_totals=totals,
               validation='All six Yes/No totals exactly match final state county returns', sources=sources)
    output.with_suffix('.source.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in audit.items() if k!='sources'},indent=2))


if __name__=='__main__':
    main()

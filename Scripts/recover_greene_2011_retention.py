"""Recover Greene County's official final 2011 appellate retention precinct returns."""
import csv
import hashlib
import html
import json
import re
import tempfile
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = 'https://greenecountypa.gov/Elections/Default.aspx?'
INDEX_URL = BASE + 'Election=24&PageLayout=PRECINCTS'
CACHE = Path(tempfile.gettempdir()) / 'pa_greene_2011'
HEADINGS = (
    'Supreme Court - Retention', 'Superior Court', 'Superior Court(2) - Retention',
    'Commonwealth Court(1) - Retention', 'Commonwealth(2) - Retention',
    'Commonwealth(3) - Retention',
)
COURTS = ('Supreme Court', 'Superior Court', 'Superior Court',
          'Commonwealth Court', 'Commonwealth Court', 'Commonwealth Court')


def fetch(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / (hashlib.sha256(url.encode()).hexdigest() + '.html')
    if cached.exists():
        return cached.read_bytes()
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=40) as response:
        raw = response.read()
    cached.write_bytes(raw)
    return raw


def parse_precinct(item):
    precinct_id, precinct = item
    url = BASE + f'PageLayout=BYPRECINCT&Election=24&Precinct={precinct_id}'
    raw = fetch(url)
    text = raw.decode('latin1')
    if 'Official Final Results' not in text or '2011 General Election' not in text:
        raise ValueError(f'Unexpected report {url}')
    results = []
    for heading in HEADINGS:
        pattern = r'<h1>'+re.escape(heading)+r'</h1><h2></h2><div id=results_module>(.*?)</div>'
        sections = re.findall(pattern, text, re.I | re.S)
        if len(sections) != 1:
            raise ValueError(f'{precinct}: expected one {heading} section; found {len(sections)}')
        section = sections[0]
        choices = {}
        for choice in ('Yes', 'No'):
            match = re.search(r'<h2>'+choice+r'</h2>.*?<td width=15% align=left>([\d,]+)</td>', section, re.I | re.S)
            if not match:
                raise ValueError(f'{precinct}: missing {heading} {choice}')
            choices[choice.lower()] = int(match[1].replace(',', ''))
        results.append(choices)
    return precinct, results, {'precinct': precinct, 'url': url, 'sha256': hashlib.sha256(raw).hexdigest()}


def recover():
    index_raw = fetch(INDEX_URL)
    index = index_raw.decode('latin1')
    if '44</span> of <span class=variable_info>44' not in index or 'Official Final Results' not in index:
        raise ValueError('Precinct index is not the 44-of-44 official final report')
    items = [(number, html.unescape(name)) for number, name in re.findall(
        r'<a href="Default\.aspx\?PageLayout=BYPRECINCT&Election=24&amp;Precinct=(\d+)">([^<]+)</a>', index)]
    if len(items) != 44 or len({number for number, _ in items}) != 44:
        raise ValueError(f'Expected 44 unique precincts, found {len(items)}')
    with ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(parse_precinct, items))
    observed = [tuple(sum(result[i][choice] for _, result, _ in reports) for choice in ('yes', 'no'))
                for i in range(6)]
    controls = {r['candidate']: (r['yes_votes'], r['no_votes'])
                for r in json.loads((ROOT / 'data/pa_historical_judicial_county_results.json').read_text())['elections']['2011']['rows']
                if r['county'] == 'GREENE' and r['is_retention']}
    by_total = {}
    for judge, total in controls.items():
        if total in by_total:
            raise ValueError('Nonunique state controls cannot identify the retention question')
        by_total[total] = judge
    if set(observed) != set(by_total) or len(set(observed)) != 6:
        audit = {'status': 'withheld_pending_reconciliation', 'observed_by_heading':
                 dict(zip(HEADINGS, observed)), 'state_by_judge': controls}
        output = ROOT / 'data/historical_sources/greene_2011_retention_reconciliation.json'
        output.write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
        raise ValueError(f'Greene returns do not match state controls; see {output}')
    rows = []
    for precinct, results, _ in reports:
        for i, choices in enumerate(results):
            judge = by_total[observed[i]]
            for choice, votes in choices.items():
                rows.append(dict(county='GREENE', precinct=precinct,
                    office=f'{COURTS[i]} Retention - {judge}', district='',
                    party=choice.upper(), candidate=choice.title(), votes=votes,
                    election_day='', mail='', provisional=''))
    output = ROOT / 'data/Openelections/2011/supplemental/greene_2011_all_retention.csv'
    with output.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    audit = {'status': 'matches_official_final_state_county_totals', 'index_url': INDEX_URL,
             'index_sha256': hashlib.sha256(index_raw).hexdigest(),
             'precinct_count': len(reports), 'row_count': len(rows),
             'heading_to_judge': {heading: by_total[observed[i]] for i, heading in enumerate(HEADINGS)},
             'totals_by_judge': {by_total[observed[i]]: dict(zip(('yes','no'), observed[i])) for i in range(6)},
             'sources': [source for _, _, source in reports]}
    output.with_suffix('.source.json').write_text(json.dumps(audit, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in audit.items() if k != 'sources'}, indent=2))


if __name__ == '__main__':
    recover()

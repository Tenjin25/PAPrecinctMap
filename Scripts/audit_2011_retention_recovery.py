"""Audit configured retention inputs without rebuilding or publishing map layers."""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import build_pa_data_layers as layers


def person_key(name):
    return re.sub(r'[^a-z0-9]', '', name.lower())


def audit():
    controls = json.loads((ROOT / 'data/pa_historical_judicial_county_results.json').read_text())
    controls = {(r['county'], person_key(r['candidate'])): r
                for r in controls['elections']['2011']['rows'] if r['is_retention']}
    buckets = defaultdict(lambda: {'yes': 0, 'no': 0, 'precincts': set(), 'sources': set()})
    zero_only_keys = set()
    original = ROOT / 'data/Openelections/2011/20111108__pa__municipal__precinct.csv'
    sources = [original, *layers.SUPPLEMENTAL_JUDICIAL_SOURCES[2011]]
    for source in sources:
        source = source.resolve()
        with source.open(encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                if ' Retention - ' not in row['office']:
                    continue
                judge = row['office'].split(' Retention - ', 1)[1]
                choice = row['candidate'].lower()
                if choice not in ('yes', 'no'):
                    raise ValueError(f'Unexpected retention choice: {row}')
                key = (row['county'], person_key(judge))
                votes = int(row['votes'])
                if votes < 0:
                    raise ValueError('Negative votes')
                if votes == 0:
                    zero_only_keys.add(key)
                    continue
                bucket = buckets[key]
                bucket[choice] += votes
                bucket['precincts'].add(row['precinct'])
                bucket['sources'].add(str(source.relative_to(ROOT)).replace('\\', '/'))
    counties = {}
    match_cache = {}
    for key, control in sorted(controls.items()):
        county, _ = key
        bucket = buckets.get(key)
        county_node = counties.setdefault(county, {})
        yes, no = (bucket['yes'], bucket['no']) if bucket else (0, 0)
        has_votes = yes + no > 0
        matched, unmatched = [], []
        if has_votes:
            for precinct in sorted(bucket['precincts']):
                cache_key = (county, precinct)
                if cache_key not in match_cache:
                    match_cache[cache_key] = layers.match_row_to_current_vtds(dict(county=county, precinct=precinct))
                (matched if match_cache[cache_key] else unmatched).append(precinct)
        exact = has_votes and (yes, no) == (control['yes_votes'], control['no_votes'])
        county_node[control['candidate']] = {
            'status': 'matches_state_county_totals' if exact else
                      'county_total_mismatch' if has_votes else
                      'zero_only_placeholder' if key in zero_only_keys else 'missing',
            'precinct_totals': {'yes': yes, 'no': no},
            'state_county_totals': {'yes': control['yes_votes'], 'no': control['no_votes']},
            'precinct_count': len(bucket['precincts']) if bucket else 0,
            'matched_precinct_labels': len(matched),
            'unmatched_precinct_labels': unmatched,
            'sources': sorted(bucket['sources']) if bucket else [],
        }
    complete = [c for c, contests in counties.items()
                if len(contests) == 6 and all(r['status'] == 'matches_state_county_totals' for r in contests.values())]
    unreconciled = {}
    for county, stem in [('HUNTINGDON', 'huntingdon'), ('NORTHUMBERLAND', 'northumberland')]:
        path = ROOT / f'data/historical_sources/{stem}_2011_retention_reconciliation.json'
        if path.exists():
            item = json.loads(path.read_text(encoding='utf-8'))
            unreconciled[county] = {
                'precinct_count': item['precinct_count'],
                'report': str(path.relative_to(ROOT)).replace('\\', '/'),
                'csv': 'data/historical_sources/' + item['extracted_csv'],
                'status': item['status'],
            }
    result = {
        'year': 2011,
        'scope': 'Six appellate retention questions only; not contested judicial elections',
        'counties_with_all_six_reconciled': complete,
        'county_count': len(counties),
        'unreconciled_counties_with_precinct_sources': unreconciled,
        'limitations': [
            'Zero-only rows do not establish recovered coverage.',
            'Label matches do not verify that historical and current precinct boundaries are identical.',
            'Northumberland is excluded pending resolution of county-versus-state source conflicts.',
            'This audit does not rebuild or publish map layers or district aggregates.',
        ],
        'counties': counties,
    }
    output = ROOT / 'data/historical_sources/2011_retention_coverage_audit.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'reconciled_counties': complete, 'output': str(output)}, indent=2))
    for county in complete:
        print(county, {j: (r['matched_precinct_labels'], len(r['unmatched_precinct_labels']))
                       for j, r in counties[county].items()})
    return result


if __name__ == '__main__':
    audit()

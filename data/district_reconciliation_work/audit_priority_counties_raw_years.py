"""Original official votes on original RDH precinct blocks in priority counties.

Strict structural/municipality matching; unresolved rows remain unallocated.
No source-control residual is redistributed, and no production file is edited.
"""
import csv
import json
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from reconcile_pa10_original_blocks import dbf_rows, key

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_county_clustered_2024_district_contests as clustered
import build_pa_data_layers as layers

OUT = Path(__file__).resolve().parent / 'priority_counties_raw_years'
COUNTIES = {'041', '043', '133', '077', '045', '101'}
OFFICES = {'USP': 'president', 'USS': 'us_senate', 'GOV': 'governor', 'ATT': 'attorney_general', 'AUD': 'auditor', 'TRE': 'treasurer'}


def normalized(fp, label):
    fragment = re.search(r'\((?:(?:Cong\.?|CD)\s*(\d+)|HD\s*(\d+)|(\d{3}))\)\s*$', label, re.I)
    qualifier = ''
    if fragment:
        qualifier = ' CD ' + str(int(fragment[1])) if fragment[1] else ' HD ' + str(int(fragment[2] or fragment[3]))
        label = label[:fragment.start()]
    fp, name = key(fp, label)
    name = re.sub(r'(?<=\d)(?=[A-Z])|(?<=[A-Z])(?=\d)', ' ', name)
    directions = {'EASTERN': 'EAST', 'WESTERN': 'WEST', 'NORTHERN': 'NORTH', 'SOUTHERN': 'SOUTH'}
    name = ' '.join(str(int(word)) if word.isdigit() else directions.get(word, word) for word in name.split())
    return fp, name + qualifier


def write(path, rows):
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def run_year(year, vap, assignments):
    archive_path = ROOT.parents[1] / f'data/pa_{year}_gen_2020_blocks.zip'
    weights = defaultdict(lambda: defaultdict(float))
    county_weights = defaultdict(lambda: defaultdict(float))
    original, collisions = {}, set()
    with zipfile.ZipFile(archive_path) as archive:
        with archive.open(next(name for name in archive.namelist() if name.lower().endswith('.dbf'))) as stream:
            for row in dbf_rows(stream):
                fp = row['COUNTYFP'].zfill(3)
                if fp not in COUNTIES:
                    continue
                identity = normalized(fp, row['PRECINCTID'])
                if identity in original and original[identity] != row['PRECINCTID']:
                    collisions.add(identity)
                original[identity] = row['PRECINCTID']
                for scope, values in assignments.items():
                    weights[(scope, *identity)][values[row['GEOID20']]] += vap[row['GEOID20']]
                    county_weights[(scope, fp)][values[row['GEOID20']]] += vap[row['GEOID20']]
    whole_counties = {}
    for identity, values in county_weights.items():
        district, population = max(values.items(), key=lambda item: item[1])
        if population / sum(values.values()) >= .999:
            whole_counties[identity] = district
    with (ROOT / f'data/ElectionReturns_{year}_General_PrecinctReturns.txt').open(newline='', encoding='utf-8-sig') as handle:
        raw = list(csv.reader(handle))
    rows, labels, matches = [], defaultdict(set), {}
    for line, parts in enumerate(raw, 1):
        if len(parts) < 29 or parts[8] not in OFFICES:
            continue
        wide = len(parts) >= 35
        fp = parts[29 if wide else 27].zfill(3)
        if fp not in COUNTIES:
            continue
        label = parts[22] if wide else ' '.join(part for part in parts[20:25] if part).strip()
        kind = parts[21 if wide else 19]
        candidate = ' '.join(parts[11:15]).upper()
        if not candidate.strip() or any(token in candidate for token in ('CAST VOTES', 'OVER VOTES', 'UNDER VOTES', 'TOTAL VOTES', 'WRITE-IN', 'WRITE IN')):
            continue
        party = parts[9].strip().upper()
        field = 'dem_votes' if party == 'DEM' else 'rep_votes' if party == 'REP' else 'other_votes'
        identity = normalized(fp, label)
        method = 'structural_label'
        typed = {'4': 'TOWNSHIP', '6': 'BOROUGH'}.get(kind)
        if typed:
            place = re.match(r'^(.*?)( \d.*)?$', identity[1])
            alternative = fp, place[1] + ' ' + typed + (place[2] or '')
            typed_parent = fp, re.sub(r' (?:CD|HD) \d+$', '', alternative[1])
            if alternative in original or typed_parent in original or any(item[0] == fp and item[1].startswith(alternative[1] + ' ') for item in original):
                identity, method = alternative, 'official_municipality_type'
        # 2018 RDH pools some congressional fragments that 2020 RDH keeps
        # separately. Only fall back to the pooled identity when no fragment
        # identity exists; the per-scope multi-label boundary guard still runs.
        if identity not in original and re.search(r' (?:CD|HD) \d+$', identity[1]):
            parent = (fp, re.sub(r' (?:CD|HD) \d+$', '', identity[1]))
            if parent in original:
                identity, method = parent, 'pooled_source_fragment_requires_single_current_district'
        if identity not in original and re.search(r'\bW\s*\d+$', label):
            children = [item for item in original if item[0] == fp and item[1].startswith(identity[1] + ' ')]
            if children == [(fp, identity[1] + ' 1')]:
                identity, method = children[0], 'unique_ward_division_1'
        matches[(fp, label, kind)] = identity, method
        labels[identity].add(label)
        rows.append({'source_line': line, 'countyfp': fp, 'precinct': label, 'municipality_type': kind,
                     'contest': OFFICES[parts[8]], 'party_bucket': field, 'candidate': candidate,
                     'source_votes': int(parts[15]), 'identity': identity, 'matching': method})
    ledger, unmatched, county_sources = [], [], defaultdict(int)
    allocated = defaultdict(int)
    for row in rows:
        identity = row['identity']
        county_sources[(row['countyfp'], row['contest'], row['party_bucket'])] += row['source_votes']
        for scope in assignments:
            current = {district: weight for district, weight in weights[(scope, *identity)].items() if weight > 0}
            reason = ('ambiguous_normalized_rdh_identity' if identity in collisions else
                      'no_exact_structural_or_municipality_match' if identity not in original else
                      'no_positive_census_vap' if not current else
                      'explicitly_localized_subrows_cross_current_boundary' if len(labels[identity]) > 1 and len(current) > 1 else '')
            allocation_method = row['matching']
            if (scope, row['countyfp']) in whole_counties:
                current = {whole_counties[(scope, row['countyfp'])]: 1.0}
                reason = ''
                allocation_method = 'whole_county_vap_join'
            if reason:
                unmatched.append({key: row[key] for key in ('source_line', 'countyfp', 'precinct', 'municipality_type', 'contest', 'candidate', 'party_bucket', 'source_votes')})
                unmatched[-1].update({'scope': scope, 'reason': reason})
                continue
            allocation = layers.allocate_votes_by_block_counts(row['source_votes'], current)
            assert sum(allocation.values()) == row['source_votes']
            for district, amount in allocation.items():
                allocated[(scope, row['countyfp'], row['contest'], district, row['party_bucket'])] += amount
            ledger.append({key: row[key] for key in ('source_line', 'countyfp', 'precinct', 'municipality_type', 'contest', 'candidate', 'party_bucket', 'source_votes', 'matching')})
            ledger[-1].update({'scope': scope, 'matching': allocation_method,
                               'matched_rdh_precinct': original.get(identity, ''),
                               'district_vap_weights': json.dumps(current, sort_keys=True),
                               'district_vote_allocations': json.dumps(allocation, sort_keys=True)})
    write(OUT / f'{year}_source_allocations.csv', ledger)
    write(OUT / f'{year}_unmatched.csv', unmatched)
    write(OUT / f'{year}_rdh_precinct_district_vap.csv', [
        {'scope': scope, 'countyfp': fp, 'normalized_identity': identity,
         'rdh_precinct': original[(fp, identity)], 'district': district, 'census_vap': value}
        for (scope, fp, identity), districts in sorted(weights.items()) for district, value in sorted(districts.items(), key=lambda item: int(item[0]))])
    write(OUT / f'{year}_county_district_votes.csv', [
        {'scope': scope, 'countyfp': fp, 'contest': contest, 'district': district, 'party_bucket': field, 'votes': votes}
        for (scope, fp, contest, district, field), votes in sorted(allocated.items())])
    return {'year': year, 'source_candidate_rows': len(rows), 'resolved_scope_rows': len(ledger),
            'unmatched_scope_rows': len(unmatched), 'unmatched_scope_votes': sum(row['source_votes'] for row in unmatched),
            'unmatched_reasons': {reason: sum(row['reason'] == reason for row in unmatched) for reason in sorted({row['reason'] for row in unmatched})},
            'normalized_rdh_collisions': sorted(collisions), 'status': 'DIAGNOSTIC_ONLY; unmatched slices must not be promoted'}


def main():
    OUT.mkdir(exist_ok=True)
    vap = clustered.load_block_vap(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz')
    assignments = clustered.load_district_assignments()
    selected_years = tuple(int(value) for value in sys.argv[1:]) if len(sys.argv) > 1 else (2016, 2018, 2020)
    assert all(year in (2016, 2018, 2020) for year in selected_years)
    summary_path = OUT / 'summary.json'
    summaries = json.loads(summary_path.read_text()) if len(sys.argv) > 1 and summary_path.exists() else []
    for year in selected_years:
        print(f'Matching original {year} votes in six priority counties', flush=True)
        result = run_year(year, vap, assignments)
        summaries = sorted([row for row in summaries if row['year'] != year] + [result], key=lambda row: row['year'])
        summary_path.write_text(json.dumps(summaries, indent=2) + '\n')
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

"""Trace official 2018 benchmark-county votes in all current legislative scopes."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_county_clustered_2024_district_contests as clustered

WORK = Path(__file__).resolve().parent
OUT = WORK / 'benchmark_counties_all_scopes_2018'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    assignments = clustered.load_district_assignments()
    weights = defaultdict(lambda: defaultdict(float))
    with (WORK / 'pa10_original_blocks/block_assignments.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            for scope, values in assignments.items():
                weights[(scope, row['countyfp'], row['source_precinct'])][values[row['block']]] += float(row['census_vap'])
    with (WORK / 'pa10_original_blocks/precinct_allocations.csv').open(newline='') as handle:
        sources = [row for row in csv.DictReader(handle) if row['model'] == 'census_vap']
    labels = defaultdict(set)
    for row in sources:
        labels[(row['countyfp'], row['matched_rdh_precinct'])].add(row['precinct'])
    allocations, unresolved, ledger = defaultdict(int), [], []
    source_totals = defaultdict(int)
    for row in sources:
        fp, precinct, field, votes = row['countyfp'], row['matched_rdh_precinct'], row['party_bucket'], int(row['source_votes'])
        source_totals[(fp, field)] += votes
        for scope in assignments:
            current = {d: value for d, value in weights[(scope, fp, precinct)].items() if value > 0}
            if not current or (len(labels[(fp, precinct)]) > 1 and len(current) > 1):
                unresolved.append({'scope': scope, 'countyfp': fp, 'source_line': row['source_line'],
                                   'precinct': row['precinct'], 'party_bucket': field, 'votes': votes,
                                   'reason': 'explicitly localized subrows cannot be pooled across a current boundary' if current else 'no positive VAP'})
                continue
            assigned = layers.allocate_votes_by_block_counts(votes, current)
            assert sum(assigned.values()) == votes
            for district, amount in assigned.items():
                allocations[(scope, fp, district, field)] += amount
                ledger.append({'year': 2018, 'contest': 'us_senate', 'scope': scope, 'countyfp': fp,
                               'source_line': row['source_line'], 'precinct': row['precinct'],
                               'official_municipality_type': row['official_municipality_type'],
                               'matched_rdh_precinct': precinct, 'candidate': row['candidate'],
                               'party_bucket': field, 'source_votes': votes, 'district': district,
                               'district_votes': amount, 'district_vap_weights': json.dumps(current, sort_keys=True)})
    save('source_precinct_allocations.csv', ledger)
    save('unresolved_localized_rows.csv', unresolved)
    differences, conservation = [], []
    county_names = {'041': 'CUMBERLAND', '043': 'DAUPHIN', '133': 'YORK'}
    for scope in assignments:
        baseline = json.loads((ROOT / f'data/district_bef_candidate/{scope}_us_senate_2018.json').read_text())
        for fp, name in county_names.items():
            before = baseline['meta']['county_conservation_audit']['counties'][name]['district_allocations']
            districts = set(before) | {district for s, c, district, field in allocations if (s, c) == (scope, fp)}
            for field in FIELDS:
                total = sum(allocations[(scope, fp, district, field)] for district in districts)
                conservation.append({'scope': scope, 'county': name, 'party_bucket': field,
                                     'source_votes': source_totals[(fp, field)], 'allocated_votes': total,
                                     'unallocated_votes': source_totals[(fp, field)] - total})
                for district in sorted(districts, key=int):
                    old = before.get(district, {}).get(field, 0)
                    new = allocations[(scope, fp, district, field)]
                    if old != new:
                        differences.append({'year': 2018, 'contest': 'us_senate', 'scope': scope,
                                            'county': name, 'countyfp': fp, 'district': district, 'party_bucket': field,
                                            'normalized_candidate_county_votes': old, 'original_precinct_blocks_county_votes': new,
                                            'direct_minus_normalized': new - old,
                                            'status': 'partial_slice_do_not_promote' if any(r['scope'] == scope and r['countyfp'] == fp for r in unresolved) else 'county_reconciled_diagnostic_only'})
    save('county_district_differences.csv', differences)
    save('county_party_conservation.csv', conservation)
    summary = {'year': 2018, 'contest': 'us_senate', 'source_candidate_rows': len(sources),
               'scopes': list(assignments), 'county_district_party_difference_rows': len(differences),
               'unresolved_rows': len(unresolved), 'unallocated_votes': sum(row['votes'] for row in unresolved),
               'county_party_conservation_failures': sum(row['unallocated_votes'] != 0 for row in conservation),
               'production_changes': []}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

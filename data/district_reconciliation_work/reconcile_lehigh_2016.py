"""Isolate Lehigh's source/bridge and original-precinct geography effects.

Diagnostic only. No published votes are changed or residuals distributed.
"""
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
OUT = WORK / 'lehigh_2016'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    maps, _, _, _ = clustered.build_vap_maps(
        ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    layers.load_vtd_current_district_blocks = lambda: maps
    direct, bridge, source = defaultdict(int), defaultdict(int), defaultdict(int)
    cache, ledger, missing = {}, [], []
    with (ROOT / 'data/ElectionReturns_2016_General_PrecinctReturns.txt').open(newline='', encoding='utf-8-sig') as handle:
        raw_codes = {str(line): parts[28] for line, parts in enumerate(csv.reader(handle), 1) if len(parts) > 28}
    with (WORK / 'priority_counties_raw_years/2016_source_allocations.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['countyfp'] != '077' or row['scope'] != 'state_house':
                continue
            label = row['precinct']
            if label not in cache:
                targets = layers.maintained_targets_for_row(
                    {'precinct': label, 'source_vtd': raw_codes[row['source_line']]}, 2016, '077')
                if not targets:
                    targets = [(*vtd, 1.0, 'current_precinct_or_vtd_name') for vtd in
                               layers.match_row_to_current_vtds({'county': 'LEHIGH', 'precinct': label})]
                weights = defaultdict(float)
                for fp, vtd, share, method in targets:
                    for district, vap in maps['state_house'].get((fp, vtd), {}).items():
                        weights[district] += share * vap
                cache[label] = targets, weights
            targets, weights = cache[label]
            votes = int(row['source_votes'])
            original = json.loads(row['district_vote_allocations'])
            old = layers.allocate_votes_by_block_counts(votes, weights) if sum(weights.values()) else {}
            contest, field = row['contest'], row['party_bucket']
            source[(contest, field)] += votes
            if not old:
                missing.append({'source_line': row['source_line'], 'precinct': label, 'votes': votes})
            else:
                assert sum(old.values()) == votes
            assert sum(original.values()) == votes
            for district in set(original) | set(old):
                direct[(contest, district, field)] += original.get(district, 0)
                bridge[(contest, district, field)] += old.get(district, 0)
                ledger.append({**{key: row[key] for key in ('source_line', 'precinct', 'municipality_type', 'contest', 'candidate', 'party_bucket', 'source_votes', 'matched_rdh_precinct')},
                               'district': district, 'raw_bridge_votes': old.get(district, 0),
                               'original_precinct_votes': original.get(district, 0),
                               'original_minus_raw_bridge': original.get(district, 0) - old.get(district, 0),
                               'original_district_vap': row['district_vap_weights'],
                               'bridge_district_vap': json.dumps(weights, sort_keys=True),
                               'bridge_vtd_targets': json.dumps(targets)})
    save('source_precinct_path_comparison.csv', ledger)
    save('unmatched.csv', missing)
    comparisons, conservation, publication_checks = [], [], []
    for contest in sorted({key[0] for key in source}):
        filename = f'state_house_{contest}_2016.json'
        candidate = json.loads((ROOT / 'data/district_bef_candidate' / filename).read_text())
        published = json.loads((ROOT / 'data/district_contests' / filename).read_text())
        baseline = candidate['meta']['county_conservation_audit']['counties']['LEHIGH']['district_allocations']
        # The published layer has no county ledger: prove full district equality
        # before treating the candidate ledger as a reproducing diagnostic.
        pub_nodes, candidate_nodes = published['general']['results'], candidate['general']['results']
        equal = all(pub_nodes[d][f] == candidate_nodes[d][f] for d in pub_nodes for f in FIELDS)
        publication_checks.append({'contest': contest, 'all_published_district_party_values_reproduced': equal})
        districts = set(baseline) | {d for c, d, f in direct if c == contest}
        for field in FIELDS:
            sums = [sum(values[(contest, d, field)] for d in districts) for values in (bridge, direct)]
            baseline_sum = sum(baseline.get(d, {}).get(field, 0) for d in districts)
            conservation.append({'contest': contest, 'party_bucket': field, 'official_source_votes': source[(contest, field)],
                                 'normalized_candidate_votes': baseline_sum, 'raw_bridge_votes': sums[0], 'original_precinct_votes': sums[1]})
            for district in sorted(districts, key=int):
                before = baseline.get(district, {}).get(field, 0)
                mid, after = bridge[(contest, district, field)], direct[(contest, district, field)]
                comparisons.append({'year': 2016, 'contest': contest, 'scope': 'state_house', 'county': 'LEHIGH',
                                    'district': district, 'party_bucket': field, 'normalized_candidate_votes': before,
                                    'raw_bridge_votes': mid, 'original_precinct_votes': after,
                                    'source_path_delta': mid - before, 'geography_path_delta': after - mid,
                                    'total_delta': after - before})
    save('county_district_path_comparison.csv', comparisons)
    save('county_party_conservation.csv', conservation)
    save('published_reproduction.csv', publication_checks)
    summary = {'unmatched_rows': len(missing), 'county_party_conservation_failures': sum(
        len({r[k] for k in ('official_source_votes', 'normalized_candidate_votes', 'raw_bridge_votes', 'original_precinct_votes')}) != 1
        for r in conservation), 'publication_checks': publication_checks,
        'changed_precinct_candidate_district_rows': sum(r['original_minus_raw_bridge'] != 0 for r in ledger),
        'production_changes': []}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

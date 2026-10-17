"""Replay source normalization without writing any production files."""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_precinct_returns as precinct
import build_pa_data_layers as layers
import build_county_clustered_2024_district_contests as clustered

OUT = Path(__file__).resolve().parent / 'lehigh_2016'


def main():
    rows = [row for row in precinct.canonical_rows(precinct.OFFICIAL_SOURCES[2016], 2016)
            if row['county'] == 'LEHIGH' and layers.is_statewide_contest_type(layers.office_mapping_for_contest(row['office']))]
    precinct.align_candidate_names(rows, 2016)
    for index, row in enumerate(rows):
        row['diagnostic_source_id'] = index
        row['diagnostic_original_precinct'] = row['precinct']
        row['diagnostic_original_votes'] = row['votes']
    joined, metadata = precinct.join_to_current_vtds(2016, rows)
    def signature(row):
        return tuple(str(row.get(field) or '') for field in precinct.FIELDS)
    stored_path = ROOT / 'data/Openelections/2016' / precinct.TARGETS[2016]
    with stored_path.open(newline='', encoding='utf-8-sig') as handle:
        all_stored = list(csv.DictReader(handle))
        stored = [r for r in all_stored if r['county'] == 'LEHIGH'
                  and layers.is_statewide_contest_type(layers.office_mapping_for_contest(r['office']))]
    expected, actual = Counter(map(signature, stored)), Counter(map(signature, joined))
    vote_fields = [field for field in precinct.FIELDS if field != 'candidate']
    vote_signature = lambda r: tuple(str(r.get(f) or '') for f in vote_fields)
    with (OUT / 'normalization_source_to_vtd.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(joined[0]))
        writer.writeheader()
        writer.writerows(joined)
    discrepancies = []
    for status, difference in [('stored_only', expected - actual), ('replay_only', actual - expected)]:
        for values, count in difference.items():
            discrepancies.append({'status': status, 'multiplicity': count, **dict(zip(precinct.FIELDS, values))})
    with (OUT / 'normalization_replay_differences.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['status', 'multiplicity', *precinct.FIELDS])
        writer.writeheader()
        writer.writerows(discrepancies)
    totals = defaultdict(lambda: [0.0, 0.0])
    for i, group in enumerate((stored, joined)):
        for row in group:
            totals[(row['office'], row['party'])][i] += float(row['votes'])
    summary = {'source_candidate_rows': len(rows), 'replayed_rows': len(joined), 'stored_rows': len(stored),
               'exact_stored_row_multiset_reproduced': expected == actual,
               'stored_vote_geography_multiset_reproduced': Counter(map(vote_signature, stored)) == Counter(map(vote_signature, joined)),
               'stored_only_rows': sum((expected - actual).values()), 'replay_only_rows': sum((actual - expected).values()),
               'crosswalk_metadata': metadata, 'party_totals': {str(k): v for k, v in totals.items()},
               'production_changes': []}
    maps, _, _, _ = clustered.build_vap_maps(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    layers.load_vtd_current_district_blocks = lambda: maps
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    # Controls require every covered county. Other counties are supplied unchanged
    # only to satisfy that check, then excluded from the diagnostic allocation.
    controlled = layers.apply_official_county_party_controls(
        joined + [r for r in all_stored if r['county'] != 'LEHIGH'], 2016)
    allocations, direct, target_cache = defaultdict(int), defaultdict(int), {}
    for row in controlled:
        if row['county'] != 'LEHIGH':
            continue
        contest = layers.office_mapping_for_contest(row['office'])
        field = 'dem_votes' if row['party'] in layers.PARTY_DEM else 'rep_votes' if row['party'] in layers.PARTY_REP else 'other_votes'
        label = row['precinct']
        if label not in target_cache:
            targets = layers.maintained_targets_for_row(row, 2016, '077')
            if not targets:
                targets = [(*vtd, 1.0, 'current_name') for vtd in layers.match_row_to_current_vtds(row)]
            weights = defaultdict(float)
            for fp, vtd, share, method in targets:
                for district, vap in maps['state_house'].get((fp, vtd), {}).items():
                    weights[district] += share * vap
            target_cache[label] = weights
        votes = layers.safe_int(row['votes'])
        assigned = layers.allocate_votes_by_block_counts(votes, target_cache[label])
        if votes and sum(assigned.values()) != votes:
            raise RuntimeError(f'Unallocated replay row: {row}')
        for district, amount in assigned.items():
            allocations[(contest, row['diagnostic_original_precinct'], district, field)] += amount
    with (OUT.parent / 'priority_counties_raw_years/2016_source_allocations.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['countyfp'] == '077' and row['scope'] == 'state_house':
                for district, amount in json.loads(row['district_vote_allocations']).items():
                    direct[(row['contest'], row['precinct'], district, row['party_bucket'])] += amount
    effects = []
    for key in sorted(set(allocations) | set(direct)):
        contest, label, district, field = key
        effects.append({'contest': contest, 'original_precinct': label, 'district': district, 'party_bucket': field,
                        'normalized_replay_votes': allocations[key], 'original_block_votes': direct[key],
                        'direct_minus_replay': direct[key] - allocations[key]})
    with (OUT / 'normalization_precinct_district_effects.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(effects[0]))
        writer.writeheader()
        writer.writerows(effects)
    checks = []
    for contest in sorted({key[0] for key in allocations}):
        baseline = json.loads((ROOT / f'data/district_bef_candidate/state_house_{contest}_2016.json').read_text())['meta']['county_conservation_audit']['counties']['LEHIGH']['district_allocations']
        for district, values in baseline.items():
            for field in ('dem_votes', 'rep_votes', 'other_votes'):
                total = sum(v for (c, p, d, f), v in allocations.items() if (c, d, f) == (contest, district, field))
                checks.append({'contest': contest, 'district': district, 'party_bucket': field,
                               'baseline_votes': values[field], 'replayed_votes': total, 'delta': total - values[field]})
    with (OUT / 'normalization_baseline_reproduction.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(checks[0]))
        writer.writeheader()
        writer.writerows(checks)
    summary['baseline_county_district_party_mismatches'] = sum(row['delta'] != 0 for row in checks)
    (OUT / 'normalization_replay_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

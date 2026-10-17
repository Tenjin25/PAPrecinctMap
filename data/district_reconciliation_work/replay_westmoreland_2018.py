"""Test source-driven Westmoreland certification/rounding stage hypotheses.

Model weights are never fitted to the retained district outcomes. Each variant
is computed from the same retained normalized source and geographic inputs.
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
from verify_diagnostic_artifacts import checksum

WORK = Path(__file__).resolve().parent
OUT = WORK / 'certification_stages_2018'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    source = ROOT / 'data/Openelections/2018/20181106__pa__general__precinct.csv'
    raw = layers.read_csv_rows(source)
    integerized = clustered.integerize_fractional_rows(raw)
    controlled = layers.apply_official_county_party_controls([dict(r) for r in integerized], 2018, contest_types={'us_senate'})
    maps, _, _, _ = clustered.build_vap_maps(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    variants = {'uncontrolled_integerized_rows': integerized, 'controlled_integerized_rows': controlled}
    allocations, totals, ledger = defaultdict(int), defaultdict(float), []
    weights_cache, missing = {}, []
    fractions = defaultdict(float)
    for model, rows in [('fractional_source', raw), *variants.items()]:
        for row_index, row in enumerate(rows):
            if row['county'].upper() != 'WESTMORELAND' or layers.office_mapping_for_contest(row['office']) != 'us_senate':
                continue
            field = 'dem_votes' if row['party'] in layers.PARTY_DEM else 'rep_votes' if row['party'] in layers.PARTY_REP else 'other_votes'
            value = float(row['votes']) if model == 'fractional_source' else layers.safe_int(row['votes'])
            totals[(model, field)] += value
            key = (row['precinct'], row.get('source_vtd', ''))
            if key not in weights_cache:
                targets = layers.maintained_targets_for_row(row, 2018, '129')
                if not targets:
                    targets = [(*vtd, 1.0, 'current_reverse_crosswalk') for vtd in layers.match_row_to_current_vtds(row)]
                weights = {scope: defaultdict(float) for scope in maps}
                for fp, vtd, share, method in targets:
                    for scope in maps:
                        for district, vap in maps[scope].get((fp, vtd), {}).items():
                            weights[scope][district] += share * vap
                weights_cache[key] = targets, weights
            targets, weights = weights_cache[key]
            for scope, district_weights in weights.items():
                if not sum(district_weights.values()):
                    missing.append({'model': model, 'row_index': row_index, 'scope': scope, 'precinct': row['precinct'], 'votes': value})
                    continue
                if model == 'fractional_source':
                    denominator = sum(district_weights.values())
                    for district, vap in district_weights.items():
                        fractions[(scope, district, field)] += value * vap / denominator
                    continue
                assigned = layers.allocate_votes_by_block_counts(int(value), district_weights)
                assert sum(assigned.values()) == value
                for district, amount in assigned.items():
                    allocations[(model, scope, district, field)] += amount
                    ledger.append({'model': model, 'source_csv_row': row_index + 2, 'precinct': row['precinct'],
                                   'candidate': row['candidate'], 'party_bucket': field, 'source_votes': int(value),
                                   'scope': scope, 'district': district, 'allocated_votes': amount,
                                   'vtd_targets': json.dumps(targets), 'district_vap_weights': json.dumps(district_weights, sort_keys=True)})
    for scope in maps:
        for field in FIELDS:
            values = {d: v for (s, d, f), v in fractions.items() if (s, f) == (scope, field)}
            result = layers.allocate_votes_by_block_counts(round(totals[('fractional_source', field)]), values)
            for district, amount in result.items():
                allocations[('uncontrolled_fractional_county_integerized', scope, district, field)] += amount
    with (OUT / 'district_party_stage_ledger.csv').open(newline='') as handle:
        stages = list(csv.DictReader(handle))
    comparisons, summaries, controls = [], [], []
    for scope in maps:
        candidate = json.loads((ROOT / f'data/district_bef_candidate/{scope}_us_senate_2018.json').read_text())
        county = candidate['meta']['county_conservation_audit']['counties']['WESTMORELAND']['district_allocations']
        for model in ('controlled_integerized_rows', 'uncontrolled_integerized_rows', 'uncontrolled_fractional_county_integerized'):
            errors = []
            for field in FIELDS:
                total = sum(v for (m, s, d, f), v in allocations.items() if (m, s, f) == (model, scope, field))
                controls.append({'model': model, 'scope': scope, 'party_bucket': field, 'allocated_votes': total,
                                 'source_or_control_votes': round(totals[('controlled_integerized_rows' if model.startswith('controlled') else 'fractional_source', field)])})
            for stage in (r for r in stages if r['scope'] == scope):
                district, field = stage['district'], stage['party_bucket'] + '_votes'
                county_votes = allocations[(model, scope, district, field)]
                other_counties = int(stage['generic_candidate']) - county.get(district, {}).get(field, 0)
                reconstructed = other_counties + county_votes
                target = int(stage['generic_candidate'] if model.startswith('controlled') else stage['retained_pre_dra'])
                error = reconstructed - target
                if error:
                    errors.append((district, field, error))
                comparisons.append({'model': model, 'scope': scope, 'district': district, 'party_bucket': field,
                                    'replayed_westmoreland_votes': county_votes, 'unchanged_other_counties_votes': other_counties,
                                    'reconstructed_district_votes': reconstructed, 'target_district_votes': target, 'delta': error})
            summaries.append({'model': model, 'scope': scope, 'district_party_mismatches': len(errors),
                              'absolute_vote_mismatch': sum(abs(r[2]) for r in errors)})
    save('westmoreland_source_row_allocations.csv', ledger)
    save('westmoreland_unmatched.csv', missing)
    save('westmoreland_variant_comparison.csv', comparisons)
    save('westmoreland_variant_conservation.csv', controls)
    summary = {'normalized_precinct_identities': len(weights_cache), 'unmatched_rows': len(missing),
               'source_party_totals': {f'{m}/{f}': v for (m, f), v in totals.items()}, 'variant_results': summaries,
               'production_changes': []}
    (OUT / 'westmoreland_replay_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    inputs = {source, ROOT / 'build_pa_data_layers.py', ROOT / 'data/BlockAssign_ST42_PA.zip'}
    for folder in ('Scripts', 'data/crosswalks', 'data/benchmarks'):
        inputs.update(p for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    inputs.update((ROOT / 'data/district_bef_audit').glob('dra_*2018*changes.csv'))
    inputs.update((ROOT / 'data/district_bef_audit').glob('dra_2018*changes.csv'))
    for scope in maps:
        for folder in ('district_bef_candidate', 'district_contests'):
            inputs.add(ROOT / f'data/{folder}/{scope}_us_senate_2018.json')
    (OUT / 'input_fingerprints.json').write_text(json.dumps(
        {p.relative_to(ROOT).as_posix(): checksum(p) for p in sorted(inputs)}, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

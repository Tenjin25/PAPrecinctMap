"""Audit original 2018 Senate precinct votes against the current Carter plan.

Diagnostic only: never uses old congressional district IDs as current IDs and
never assigns unmatched votes or unexplained residuals to any district.
"""
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_county_clustered_2024_district_contests as clustered

OUT = Path(__file__).resolve().parent / 'pa10_raw_returns'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    path = ROOT / 'data/ElectionReturns_2018_General_PrecinctReturns.txt'
    maps, _, _, _ = clustered.build_vap_maps(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    layers.load_vtd_current_district_blocks = lambda: maps
    cache, records, unmatched = {}, [], []
    totals = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    old = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    source = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    with path.open(encoding='utf-8-sig', newline='') as handle:
        for index, parts in enumerate(csv.reader(handle), 1):
            if len(parts) < 31 or parts[8] != 'USS' or parts[29].zfill(3) not in {'041', '043', '133'}:
                continue
            party, fp, precinct, votes = parts[9], parts[29].zfill(3), parts[22], int(parts[15])
            if party not in {'DEM', 'REP', 'GRN', 'LIB'}:
                raise ValueError(f'Unexpected named-candidate party {party}')
            bucket = 'dem_votes' if party == 'DEM' else 'rep_votes' if party == 'REP' else 'other_votes'
            source[fp][bucket] += votes
            if parts[18] == '10':
                old[fp][bucket] += votes
            key = (fp, precinct)
            if key not in cache:
                targets = layers.maintained_targets_for_row({'precinct': precinct}, 2018, fp)
                weights = defaultdict(float)
                for county, vtd, share, method in targets:
                    for district, vap in maps['congressional'].get((county, vtd), {}).items():
                        weights[district] += share * vap
                cache[key] = (targets, weights)
            targets, weights = cache[key]
            denominator = sum(weights.values())
            fraction = weights.get('10', 0) / denominator if denominator else None
            allocation = layers.allocate_votes_by_block_counts(votes, weights) if denominator else {}
            if not denominator:
                unmatched.append({'source_line': index, 'countyfp': fp, 'precinct': precinct, 'party': party, 'votes': votes})
            else:
                assert sum(allocation.values()) == votes
                totals[fp][bucket] += allocation.get('10', 0)
            records.append({'source_line': index, 'countyfp': fp, 'precinct': precinct,
                            'raw_precinct_code': parts[3], 'old_2018_congressional_district': parts[18],
                            'party_bucket': bucket, 'candidate': ' '.join(parts[11:15]),
                            'source_votes': votes, 'current_cd10_fraction': fraction,
                            'current_cd10_fractional_votes': votes * fraction if fraction is not None else '',
                            'current_cd10_integer_votes': allocation.get('10', 0) if denominator else '',
                            'all_district_allocations': json.dumps(allocation, sort_keys=True),
                            'targets': json.dumps(targets),
                            'status': 'matched' if denominator else 'unmatched_do_not_allocate',
                            'mail_label': any(token in precinct.upper() for token in ('MAIL', 'ABSENT', 'PROVISION'))})
    save('source_precinct_allocation.csv', records)
    save('unmatched.csv', unmatched)
    controls = {}
    with (ROOT / 'data/benchmarks/pa_county_2018_us_senate_certified.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            name = row['county'].upper()
            fp = {'CUMBERLAND': '041', 'DAUPHIN': '043', 'YORK': '133'}.get(name)
            if fp:
                controls[fp] = {field: int(row[field]) for field in FIELDS}
    assert dict(source) == controls
    candidate = json.loads((ROOT / 'data/district_bef_candidate/congressional_us_senate_2018.json').read_text())
    county_comparison = []
    for fp, name in [('041', 'CUMBERLAND'), ('043', 'DAUPHIN'), ('133', 'YORK')]:
        exact = candidate['meta']['county_conservation_audit']['counties'][name]['district_allocations']['10']
        for field in FIELDS:
            county_comparison.append({'countyfp': fp, 'county': name, 'party_bucket': field,
                                     'official_county_votes': source[fp][field],
                                     'raw_precinct_current_cd10': totals[fp][field],
                                     'normalized_candidate_current_cd10': exact[field],
                                     'raw_minus_normalized': totals[fp][field] - exact[field],
                                     'cause': 'source-path composition and integerization; not an observed fragment tally'})
    save('county_source_path_comparison.csv', county_comparison)
    summary = {'source': str(path.relative_to(ROOT)), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
               'source_lf_sha256': hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
               'source_county_votes': dict(source), 'current_cd10_county_votes': dict(totals),
               'old_2018_cd10_county_votes': dict(old), 'unmatched_rows': len(unmatched),
               'unmatched_votes': sum(row['votes'] for row in unmatched),
               'precincts': len(cache), 'split_precincts': [
                   {'countyfp': fp, 'precinct': precinct, 'district_vap_weights': dict(weights), 'targets': targets}
                   for (fp, precinct), (targets, weights) in cache.items() if len(weights) > 1],
               'decision': 'Diagnostic only; matching and precinct vintage require independent review before promotion.'}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key != 'split_precincts'}, indent=2))


if __name__ == '__main__':
    main()

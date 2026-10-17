"""Inventory reverse-crosswalk exposure, not inferred vote corrections."""
import csv
import json
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_pa_precinct_returns as precinct
import build_county_clustered_2024_district_contests as clustered

OUT = Path(__file__).resolve().parent / 'reverse_crosswalk_exposure'


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    maps, _, _, _ = clustered.build_vap_maps(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    reverse = defaultdict(list)
    with (ROOT / 'data/crosswalks/pa_vtd20_to_current_precinct.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            reverse[(row['current_countyfp'], row['current_precinct_norm'])].append(row)
    risk, evidence = {}, []
    for (fp, label), rows in reverse.items():
        source_keys = {(r['countyfp'], r['vtd20']) for r in rows}
        if len(source_keys) <= 1:
            continue
        for scope in maps:
            weights = defaultdict(float)
            for source in source_keys:
                for district, vap in maps[scope].get(source, {}).items():
                    weights[district] += vap
            if len([v for v in weights.values() if v > 0]) <= 1:
                continue
            risk[(fp, label, scope)] = weights
            for row in rows:
                evidence.append({'countyfp': fp, 'current_precinct': label, 'scope': scope,
                                 'source_countyfp': row['countyfp'], 'source_vtd20': row['vtd20'],
                                 'forward_share': row['weight'], 'forward_method': row['method'],
                                 'source_vtd_district_vap': json.dumps(maps[scope].get((row['countyfp'], row['vtd20']), {}), sort_keys=True),
                                 'full_reverse_union_district_vap': json.dumps(weights, sort_keys=True),
                                 'status': 'cross_boundary_exposure_not_an_adjudicated_error'})
    names = layers.county_fips_by_name()
    grouped = defaultdict(lambda: [0, Decimal(0), set()])
    sources = []
    for year, filename in sorted(precinct.TARGETS.items()):
        path = ROOT / 'data/Openelections' / str(year) / filename
        if not path.exists():
            continue
        with path.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.DictReader(handle)
            if 'county' not in (reader.fieldnames or []):
                continue
            sources.append(str(path.relative_to(ROOT)).replace('\\', '/'))
            for row in reader:
                contest = layers.office_mapping_for_contest(row['office'])
                if not layers.is_statewide_contest_type(contest):
                    continue
                county = layers.normalize_county_name(row['county'])
                fp = names.get(county, '')
                party = row['party'].upper()
                bucket = 'dem_votes' if party in layers.PARTY_DEM else 'rep_votes' if party in layers.PARTY_REP else 'other_votes'
                for scope in maps:
                    if (fp, row['precinct'], scope) in risk:
                        values = grouped[(year, contest, scope, county, fp, bucket)]
                        values[0] += 1
                        values[1] += Decimal(row['votes'] or '0')
                        values[2].add(row['precinct'])
    save('cross_boundary_keys.csv', evidence)
    summary_rows = [{'year': y, 'contest': c, 'scope': s, 'county': n, 'countyfp': fp, 'party_bucket': f,
                     'exposed_source_rows': values[0], 'exposed_source_votes': str(values[1]),
                     'exposed_current_precincts': len(values[2]),
                     'cause': 'reverse_many_to_many_crosswalk_full_vtd_union',
                     'status': 'exposure_only_not_a_vote_delta'}
                    for (y, c, s, n, fp, f), values in sorted(grouped.items())]
    save('year_contest_scope_county_exposure.csv', summary_rows)
    summary = {'cross_boundary_key_scope_pairs': len(risk), 'counties': len({k[0] for k in risk}),
               'keys_by_scope': {scope: sum(k[2] == scope for k in risk) for scope in maps},
               'normalized_source_files_scanned': sources, 'grouped_exposure_rows': len(summary_rows),
               'years_with_exposure': sorted({r['year'] for r in summary_rows}),
               'warning': 'Stored normalized-file exposure only; does not prove every row follows the reverse fallback or adjudicate vote changes.',
               'production_changes': []}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'normalized_source_files_scanned'}, indent=2))


if __name__ == '__main__':
    main()

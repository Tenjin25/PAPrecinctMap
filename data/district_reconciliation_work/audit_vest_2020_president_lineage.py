"""Rebuild the retained VEST -> geometry -> DRA -> control 2020 pipeline."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'stage_lineage'
sys.path.insert(0, str(ROOT / 'Scripts'))
import regenerate_pa_district_jsons_from_crosswalks as regen

FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')
SCOPES = ('congressional', 'state_house', 'state_senate')


def digest(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.json', '.md', '.py', '.txt'}:
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def snapshot(results):
    return {
        district: {field: int(row.get(field) or 0) for field in FIELDS}
        for district, row in results.items()
    }


def save_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--source', type=Path, required=True,
        help='Path to the supplied pa_2020.zip archive (not stored in Git)',
    )
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.exists():
        raise FileNotFoundError(f'Supplied VEST 2020 archive not found: {source}')

    control_path = ROOT / 'data/vest_2020_district_vote_audit.json'
    controls = json.loads(control_path.read_text(encoding='utf-8'))['controls']['president']
    controls = {field: int(controls[field]) for field in FIELDS[:3]}
    stage_rows = []
    scope_by_results = {}

    original_dra = regen.apply_dra_district_shares
    original_benchmark = regen.apply_exact_district_benchmarks
    original_control = regen.apply_statewide_vote_control

    def record(scope, stage, before, after):
        filename = f'{scope}_president_2020.json'
        for district in sorted(after, key=int):
            stage_rows.append({
                'file': filename, 'year': 2020, 'contest': 'president',
                'scope': scope, 'district': district, 'stage': stage,
                **{f'old_{field}': before[district][field] for field in FIELDS},
                **{f'new_{field}': after[district][field] for field in FIELDS},
            })

    def dra(scope, contest, year, results):
        before = snapshot(results)
        scope_by_results[id(results)] = scope
        label = original_dra(scope, contest, year, results)
        if label:
            record(scope, 'dra_share_calibration', before, snapshot(results))
        return label

    def benchmark(scope, contest, year, results):
        before = snapshot(results)
        scope_by_results[id(results)] = scope
        label = original_benchmark(scope, contest, year, results)
        if label:
            record(scope, 'exact_district_benchmark', before, snapshot(results))
        return label

    def controlled(contest, year, results, *control_args, **control_kwargs):
        scope = scope_by_results.get(id(results))
        if not scope:
            raise RuntimeError('2020 control stage has no registered scope')
        before = snapshot(results)
        original_control(contest, year, results, *control_args, **control_kwargs)
        record(scope, 'vest_source_statewide_control', before, snapshot(results))
        before_certified = snapshot(results)
        label = original_control(
            contest, year, results, controls_override=controls,
            source_override='data/vest_2020_district_vote_audit.json',
        )
        record(scope, 'certified_statewide_control', before_certified, snapshot(results))
        return label

    endpoints = []
    with tempfile.TemporaryDirectory(prefix='_vest_2020_', dir=OUT) as temporary:
        target = Path(temporary)
        regen.apply_dra_district_shares = dra
        regen.apply_exact_district_benchmarks = benchmark
        regen.apply_statewide_vote_control = controlled
        try:
            regen.build_one(
                2020,
                ROOT / 'data/ElectionReturns_2020_General_PrecinctReturns.txt',
                'president', 'USP', target, 'block_count', list(SCOPES),
                historical_vtd_source=source,
                historical_geometry_source=source,
            )
        finally:
            regen.apply_dra_district_shares = original_dra
            regen.apply_exact_district_benchmarks = original_benchmark
            regen.apply_statewide_vote_control = original_control

        for scope in SCOPES:
            filename = f'{scope}_president_2020.json'
            rebuilt = json.loads((target / filename).read_text(encoding='utf-8'))
            published = json.loads((ROOT / 'data/district_contests' / filename).read_text(encoding='utf-8'))
            audit = rebuilt['meta']
            if audit['unmatched_source_vtds'] != 0 or audit['unmatched_source_votes'] != 0:
                raise RuntimeError(f'Unmatched 2020 VEST source rows in {scope}')
            if audit['district_membership_gap_votes'] != 0 or audit['district_membership_gap_keys']:
                raise RuntimeError(f'2020 VEST membership gap in {scope}')
            for district, row in rebuilt['general']['results'].items():
                expected = published['general']['results'][district]
                if any(int(row[field]) != int(expected[field]) for field in FIELDS):
                    raise RuntimeError(f'2020 publication mismatch: {filename} district {district}')
                if row.get('dem_candidate') != expected.get('dem_candidate') or row.get('rep_candidate') != expected.get('rep_candidate'):
                    raise RuntimeError(f'2020 candidate-name mismatch: {filename} district {district}')
                endpoints.append({
                    'file': filename, 'year': 2020, 'contest': 'president',
                    'scope': scope, 'district': district,
                    **{field: int(row[field]) for field in FIELDS},
                    'unmatched_source_vtds': audit['unmatched_source_vtds'],
                    'unmatched_source_votes': audit['unmatched_source_votes'],
                    'district_membership_gap_votes': audit['district_membership_gap_votes'],
                    'candidate_names_preserved': True,
                    'lineage_eligible': True,
                })

    source_votes, _candidates = regen.parse_historical_vtd_returns(source, 2020, 'USP')
    county_rows = []
    by_county = {}
    for (county, _precinct, _name), values in source_votes.items():
        counter = by_county.setdefault(county, Counter())
        for party in ('dem', 'rep', 'other'):
            counter[f'{party}_votes'] += round(float(values.get(party) or 0))
    for county, counter in sorted(by_county.items()):
        county_rows.append({
            'county_fips': county,
            **{field: int(counter[field]) for field in FIELDS[:3]},
            'total_votes': sum(int(counter[field]) for field in FIELDS[:3]),
            'status': 'retained_source_total_before_dra_and_statewide_control',
        })

    fingerprints = {
        'supplied_archive': {'filename': source.name, 'sha256': digest(source)},
        'tracked_inputs': {
            'data/district_reconciliation_work/audit_vest_2020_president_lineage.py': digest(Path(__file__)),
            'Scripts/regenerate_pa_district_jsons_from_crosswalks.py': digest(ROOT / 'Scripts/regenerate_pa_district_jsons_from_crosswalks.py'),
            'data/district-statistics state house 2020 Pres.csv': digest(ROOT / 'data/district-statistics state house 2020 Pres.csv'),
            'data/district-statistics state senate 2020 Pres.csv': digest(ROOT / 'data/district-statistics state senate 2020 Pres.csv'),
            'data/benchmarks/pa_congressional_2020_president.csv': digest(ROOT / 'data/benchmarks/pa_congressional_2020_president.csv'),
            'data/vest_2020_district_vote_audit.json': digest(control_path),
        },
    }
    save_csv(OUT / 'vest_2020_president_endpoints.csv', endpoints)
    save_csv(OUT / 'vest_2020_president_stage_ledger.csv', stage_rows)
    save_csv(OUT / 'vest_2020_president_source_counties.csv', county_rows)
    (OUT / 'vest_2020_president_input_fingerprints.json').write_text(
        json.dumps(fingerprints, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    summary = {
        'endpoint_rows': len(endpoints),
        'stage_rows': len(stage_rows),
        'source_counties': len(county_rows),
        'scopes': list(SCOPES),
        'zero_unmatched_source_vtds': True,
        'zero_district_membership_gap_votes': True,
        'all_published_votes_reproduced': True,
        'candidate_names_preserved': True,
        'source_statewide_party_totals': {
            field: sum(int(row[field]) for row in county_rows) for field in FIELDS
        },
        'certified_statewide_party_controls': {
            **controls, 'total_votes': sum(controls.values())
        },
        'classification': 'exact numerical publication lineage; not a production correction',
        'county_note': 'county source totals precede DRA and the explicit retained statewide control; post-control county attribution is not inferred',
        'production_changes': [],
    }
    (OUT / 'vest_2020_president_summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

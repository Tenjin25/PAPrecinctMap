"""Rebuild missing judicial county/allocation evidence from retained sources."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_county_clustered_2024_district_contests as clustered

WORK = Path(__file__).resolve().parent
OUT = WORK / 'judicial_evidence'


def stable_hash(path):
    data = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.txt', '.py', '.md'}:
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('years', nargs='*', type=int, default=[2001])
    args = parser.parse_args()
    requested = set(args.years or [2001])
    build = OUT / ('candidate_' + '_'.join(str(year) for year in sorted(requested)))
    acceptance = json.loads((WORK / 'report/acceptance_integration.json').read_text(encoding='utf-8'))
    missing = {
        item['file'] for item in acceptance['missing_county_evidence_files']
        if int(item['year']) in requested
    }
    if not missing:
        raise SystemExit(f'No missing judicial evidence files for {sorted(requested)}')
    contests = {item['contest'] for item in acceptance['missing_county_evidence_files'] if int(item['year']) in requested}
    build.mkdir(parents=True, exist_ok=True)
    maps, _county_districts, vap_blocks, carter_blocks = clustered.build_vap_maps(
        ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip'
    )
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    original = layers.read_csv_rows
    cache = {}

    def integerized(path):
        key = str(Path(path).resolve())
        if key not in cache:
            cache[key] = clustered.integerize_fractional_rows(original(path))
        return cache[key]

    layers.read_csv_rows = integerized
    try:
        layers.build_district_manifests(
            build,
            contest_types=contests,
            years=requested,
            require_county_manifest=False,
        )
    finally:
        layers.read_csv_rows = original

    evidence_rows = []
    district_changes = []
    county_allocations = []
    candidate_name_changes = []
    fingerprints = {}
    for year in sorted(requested):
        source_path = layers.OFFICIAL_JUDICIAL_SOURCES.get(year)
        if source_path and source_path.exists():
            source_path = source_path.resolve()
            fingerprints[source_path.relative_to(ROOT).as_posix()] = stable_hash(source_path)
    for name in sorted(missing):
        rebuilt_path = build / name
        if not rebuilt_path.exists():
            evidence_rows.append({
                'file': name, 'status': 'official_source_has_no_rows_for_contest',
                'blocker': 'retained official source contains no rows for this contest; publication totals were not used',
            })
            continue
        payload = json.loads(rebuilt_path.read_text(encoding='utf-8'))
        allocation = payload.get('meta', {}).get('allocation_audit') or {}
        county = payload.get('meta', {}).get('county_conservation_audit') or {}
        source_year = int(payload.get('year') or 0)
        source_path = layers.OFFICIAL_JUDICIAL_SOURCES.get(source_year)
        if source_path:
            source_path = source_path.resolve()
        if source_path and source_path.exists():
            fingerprints[source_path.relative_to(ROOT).as_posix()] = stable_hash(source_path)
        evidence_rows.append({
            'file': name, 'year': source_year, 'contest': payload.get('contest_type'),
            'scope': payload.get('scope'), 'status': (
                'recovered' if allocation and county else 'missing_rebuilt_evidence'
            ),
            'source_rows': allocation.get('source_rows', ''),
            'source_votes': allocation.get('source_votes', ''),
            'unmatched_rows': allocation.get('unmatched_rows', ''),
            'unallocated_rows': allocation.get('unallocated_rows', ''),
            'matched_votes_conserved': allocation.get('conserved_for_matched_rows', ''),
            'county_count': county.get('county_count', ''),
            'county_failures': county.get('failure_count', ''),
            'all_counties_conserved': county.get('all_counties_conserved', ''),
            'candidate_file_sha256': stable_hash(rebuilt_path),
            'official_source': source_path.relative_to(ROOT).as_posix() if source_path else '',
            'official_source_sha256': stable_hash(source_path) if source_path and source_path.exists() else '',
        })
        baseline_path = ROOT / 'data/district_bef_candidate' / name
        baseline = json.loads(baseline_path.read_text(encoding='utf-8')) if baseline_path.exists() else {'general': {'results': {}}}
        before = baseline.get('general', {}).get('results', {})
        after = payload.get('general', {}).get('results', {})
        for district in sorted(set(before) | set(after), key=lambda value: int(value)):
            old, new = before.get(district, {}), after.get(district, {})
            deltas = {
                field: int(new.get(field) or 0) - int(old.get(field) or 0)
                for field in ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')
            }
            if any(deltas.values()) or district not in before or district not in after:
                district_changes.append({
                    'file': name, 'year': source_year, 'contest': payload.get('contest_type'),
                    'scope': payload.get('scope'), 'district': district,
                    **{f'before_{field}': int(old.get(field) or 0) for field in deltas},
                    **{f'after_{field}': int(new.get(field) or 0) for field in deltas},
                    **{f'delta_{field}': value for field, value in deltas.items()},
                    'status': 'recovered_evidence_candidate_not_approved',
                })
            for field in ('dem_candidate', 'rep_candidate'):
                if str(old.get(field) or '') != str(new.get(field) or ''):
                    candidate_name_changes.append({
                        'file': name, 'district': district, 'field': field,
                        'before': old.get(field) or '', 'after': new.get(field) or '',
                    })
        for county_name, county_row in sorted((county.get('counties') or {}).items()):
            for district, values in sorted((county_row.get('district_allocations') or {}).items(), key=lambda item: int(item[0])):
                county_allocations.append({
                    'file': name, 'year': source_year, 'contest': payload.get('contest_type'),
                    'scope': payload.get('scope'), 'county': county_name, 'district': district,
                    **{field: int(values.get(field) or 0) for field in ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')},
                })
    OUT.mkdir(exist_ok=True)
    fields = sorted({key for row in evidence_rows for key in row}, key=lambda key: (key != 'file', key))
    with (OUT / 'recovery_ledger.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(evidence_rows)
    for filename, rows in (
        ('district_vote_changes.csv', district_changes),
        ('county_district_allocations.csv', county_allocations),
        ('candidate_name_changes.csv', candidate_name_changes),
    ):
        with (OUT / filename).open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        'years': sorted(requested), 'requested_files': len(missing),
        'recovered_files': sum(row.get('status') == 'recovered' for row in evidence_rows),
        'blocked_files': [row['file'] for row in evidence_rows if row.get('status') != 'recovered'],
        'county_conservation_failures': sum(int(row.get('county_failures') or 0) for row in evidence_rows),
        'unmatched_rows': sum(int(row.get('unmatched_rows') or 0) for row in evidence_rows),
        'unallocated_rows': sum(int(row.get('unallocated_rows') or 0) for row in evidence_rows),
        'changed_district_rows_against_prior_candidate': len(district_changes),
        'county_district_allocation_rows': len(county_allocations),
        'candidate_name_changes_against_prior_candidate': len(candidate_name_changes),
        'vap_blocks': vap_blocks, 'carter_blocks': carter_blocks,
        'source_policy': 'retained official precinct sources only; never published district totals',
        'production_changes': [],
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (OUT / 'input_fingerprints.json').write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

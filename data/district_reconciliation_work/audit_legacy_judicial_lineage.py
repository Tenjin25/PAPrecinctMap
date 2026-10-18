"""Verify the Carter-adjusted historical judicial publication replay."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'stage_lineage'
HISTORICAL_COMMIT = '6f5f0fba26a60164cac6fceca0e9f8693d6fb8a3'
NAME_COMMIT = '2afe1f6d4751093be19210136f13be8037c893cf'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')
SOURCE_YEARS = (2001, 2003, 2007, 2015, 2017, 2019, 2021, 2023, 2025)


def run_git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ['git', *args], cwd=cwd, check=True, capture_output=True,
        text=True, encoding='utf-8', errors='replace',
    )
    return result.stdout.strip()


def digest(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.json', '.md', '.py', '.txt'}:
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def save_csv(path: Path, rows: list[dict], fallback_fields: list[str]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else fallback_fields)
        writer.writeheader()
        writer.writerows(rows)


def judicial(row: dict[str, str]) -> bool:
    contest = row['contest']
    return 'court' in contest or 'retention' in contest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--historical-worktree', type=Path, required=True)
    parser.add_argument(
        '--candidate-directory', default='data/legacy_judicial_replay_all',
        help='Path relative to the historical worktree for replay output',
    )
    parser.add_argument('--rebuild', action='store_true')
    args = parser.parse_args()
    historical = args.historical_worktree.resolve()
    if run_git(historical, 'rev-parse', 'HEAD') != HISTORICAL_COMMIT:
        raise RuntimeError(f'Historical worktree must be detached at {HISTORICAL_COMMIT}')

    with (WORK / 'report/all_district_differences.csv').open(newline='', encoding='utf-8-sig') as handle:
        differences = [row for row in csv.DictReader(handle) if judicial(row)]
    contests = sorted({row['contest'] for row in differences})
    candidate = historical / args.candidate_directory
    if args.rebuild:
        candidate.mkdir(parents=True, exist_ok=True)
        code = (
            "import os; from pathlib import Path; import build_pa_data_layers as b; "
            "out=Path(os.environ['JUDICIAL_OUTPUT']); out.mkdir(parents=True, exist_ok=True); "
            "b.build_district_manifests(out, contest_types=os.environ['JUDICIAL_CONTESTS'].split(','))"
        )
        environment = dict(os.environ)
        environment['JUDICIAL_OUTPUT'] = args.candidate_directory
        environment['JUDICIAL_CONTESTS'] = ','.join(contests)
        subprocess.run([sys.executable, '-c', code], cwd=historical, env=environment, check=True)
    if not candidate.exists():
        raise FileNotFoundError(f'Historical replay output not found: {candidate}')

    endpoints = []
    label_changes = []
    cache = {}
    publication_files = sorted({row['file'] for row in differences})
    for filename in publication_files:
        historical_path = candidate / filename
        published_path = ROOT / 'data/district_contests' / filename
        if not historical_path.exists():
            raise RuntimeError(f'Historical replay did not emit {filename}')
        cache[('historical', filename)] = json.loads(historical_path.read_text(encoding='utf-8'))
        cache[('published', filename)] = json.loads(published_path.read_text(encoding='utf-8'))
        if run_git(ROOT, 'diff', '--quiet', NAME_COMMIT, '--', f'data/district_contests/{filename}'):
            raise RuntimeError(f'Current publication differs from name-preservation commit: {filename}')

    for row in differences:
        filename, district = row['file'], row['district']
        legacy = cache[('historical', filename)]['general']['results'][district]
        published = cache[('published', filename)]['general']['results'][district]
        if any(int(legacy.get(field) or 0) != int(published.get(field) or 0) for field in FIELDS):
            raise RuntimeError(f'Historical judicial replay mismatch: {filename} district {district}')
        names_equal = all(
            str(legacy.get(field) or '') == str(published.get(field) or '')
            for field in ('dem_candidate', 'rep_candidate')
        )
        endpoints.append({
            'file': filename, 'year': int(row['year']), 'contest': row['contest'],
            'scope': row['scope'], 'district': district,
            **{field: int(published.get(field) or 0) for field in FIELDS},
            'legacy_dem_candidate': legacy.get('dem_candidate') or '',
            'legacy_rep_candidate': legacy.get('rep_candidate') or '',
            'published_dem_candidate': published.get('dem_candidate') or '',
            'published_rep_candidate': published.get('rep_candidate') or '',
            'candidate_names_equal_before_name_stage': names_equal,
            'candidate_names_preserved_by_name_commit': True,
            'lineage_eligible': True,
        })
        if not names_equal:
            for field in ('dem_candidate', 'rep_candidate'):
                if str(legacy.get(field) or '') != str(published.get(field) or ''):
                    label_changes.append({
                        'file': filename, 'year': int(row['year']), 'contest': row['contest'],
                        'scope': row['scope'], 'district': district, 'field': field,
                        'historical_value': legacy.get(field) or '',
                        'published_value': published.get(field) or '',
                        'stage': 'candidate_name_preservation_at_2afe1f6',
                    })

    tracked_inputs = [
        'build_pa_data_layers.py',
        'data/crosswalks/pa_block20_to_vtd20.csv',
        'data/crosswalks/pa_historical_precinct_to_vtd20.csv',
        'data/crosswalks/pa_modern_precinct_to_vtd20.csv',
        'data/crosswalks/pa_vtd10_to_vtd20_block_chain.csv',
        'data/crosswalks/pa_vtd20_to_current_precinct.csv',
        'data/42_PA_CD118.txt', 'data/42_PA_SLDL22.txt', 'data/42_PA_SLDU22.txt',
    ] + [
        f'data/ElectionReturns_{year}_{"General" if year in {2019} else "Municipal"}_PrecinctReturns.txt'
        for year in SOURCE_YEARS if year != 2015
    ] + ['data/ElectionReturns_2015_Municipal_Precinct.txt']
    fingerprints = {
        'historical_commit': HISTORICAL_COMMIT,
        'candidate_name_commit': NAME_COMMIT,
        'historical_inputs': {
            path: {'sha256': digest(historical / path), 'git_blob': run_git(historical, 'rev-parse', f'{HISTORICAL_COMMIT}:{path}')}
            for path in tracked_inputs
        },
        'name_stage_git_blob': run_git(ROOT, 'rev-parse', f'{NAME_COMMIT}:Scripts/restore_district_candidate_names.py'),
        'audit_script_lf_sha256': digest(Path(__file__)),
    }
    save_csv(OUT / 'legacy_judicial_endpoints.csv', endpoints, ['file'])
    save_csv(OUT / 'legacy_judicial_label_normalizations.csv', label_changes, ['file'])
    (OUT / 'legacy_judicial_input_fingerprints.json').write_text(
        json.dumps(fingerprints, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    summary = {
        'endpoint_rows': len(endpoints),
        'publication_files': len(publication_files),
        'contest_year_groups': len({(row['year'], row['contest']) for row in differences}),
        'exact_numeric_rows': len(endpoints),
        'numeric_mismatches': 0,
        'rows_with_legacy_candidate_names_equal': sum(
            row['candidate_names_equal_before_name_stage'] for row in endpoints
        ),
        'rows_requiring_name_preservation_stage': sum(
            not row['candidate_names_equal_before_name_stage'] for row in endpoints
        ),
        'label_field_changes': len(label_changes),
        'current_files_equal_name_commit': True,
        'historical_commit': HISTORICAL_COMMIT,
        'candidate_name_commit': NAME_COMMIT,
        'classification': 'exact historical numerical publication lineage; geography and modern official-source replacement remain separate decisions',
        'production_changes': [],
    }
    (OUT / 'legacy_judicial_summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

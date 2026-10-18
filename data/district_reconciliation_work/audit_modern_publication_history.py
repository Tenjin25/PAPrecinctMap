"""Extract exact directed 2022/2024 publication stages from retained commits."""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'stage_lineage'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')
SEQUENCES = {
    2022: [
        ('334c7e51869922f27b17544b5b55fc444de77700', 'historical_rdh_2022_publication_endpoint'),
        ('80f94d3d96b8c7d507d8a390177cdbb35089143b', 'county_clustered_allocation'),
        ('bfc2f39ca41db67ab347fe04962a88342df63d9f', 'certified_county_party_control'),
    ],
    2024: [
        ('94fb75a72b7ca7d633bc855ad08dd7b3186a8ddf', 'historical_rdh_2024_publication_endpoint'),
        ('bd4defcda049e14d06a8fc0ea166f472ce6a706e', 'vap_controlled_allocation'),
        ('36afe313aa2573f9ebe1ba6b5121c4e586d1cbea', 'localized_residual_allocation'),
        ('80f94d3d96b8c7d507d8a390177cdbb35089143b', 'county_clustered_allocation'),
        ('bfc2f39ca41db67ab347fe04962a88342df63d9f', 'certified_county_metadata_stage'),
    ],
}


def git(*args: str, check: bool = True) -> str:
    result = subprocess.run(
        ['git', *args], cwd=ROOT, capture_output=True, check=check,
        text=True, encoding='utf-8', errors='replace',
    )
    return result.stdout.strip()


def digest(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.json', '.md', '.py', '.txt'}:
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def snapshot(commit: str, filename: str, cache: dict) -> dict:
    key = (commit, filename)
    if key not in cache:
        cache[key] = json.loads(git('show', f'{commit}:data/district_contests/{filename}'))
    return cache[key]


def vector(row: dict) -> tuple[int, ...]:
    return tuple(int(row.get(field) or 0) for field in FIELDS)


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    target_path = OUT / 'modern_publication_target_rows.csv'
    with target_path.open(newline='', encoding='utf-8-sig') as handle:
        targets = list(csv.DictReader(handle))
    if len(targets) != 62:
        raise RuntimeError(f'Expected 62 retained target rows, found {len(targets)}')

    cache = {}
    endpoints, stages = [], []
    file_blob_fingerprints = {}
    for target in targets:
        year = int(target['year'])
        filename, district = target['file'], target['district']
        sequence = SEQUENCES[year]
        published = json.loads((ROOT / 'data/district_contests' / filename).read_text(encoding='utf-8'))
        published_row = published['general']['results'][district]
        values = []
        for commit, stage in sequence:
            payload = snapshot(commit, filename, cache)
            values.append((commit, stage, payload['general']['results'][district]))
            file_blob_fingerprints[f'{commit}:data/district_contests/{filename}'] = git(
                'rev-parse', f'{commit}:data/district_contests/{filename}'
            )
        if vector(values[-1][2]) != vector(published_row):
            raise RuntimeError(f'Final historical stage does not match publication: {filename} district {district}')
        if any(
            str(values[-1][2].get(field) or '') != str(published_row.get(field) or '')
            for field in ('dem_candidate', 'rep_candidate')
        ):
            raise RuntimeError(f'Candidate name mismatch in final stage: {filename} district {district}')
        first_commit, first_stage, first_row = values[0]
        endpoints.append({
            **target,
            **{field: int(first_row.get(field) or 0) for field in FIELDS},
            'stage': first_stage, 'source_commit': first_commit,
            'candidate_names_preserved': True, 'lineage_eligible': True,
        })
        for (old_commit, _old_stage, old), (new_commit, stage, new) in zip(values, values[1:]):
            if vector(old) == vector(new):
                continue
            stages.append({
                **target, 'stage': stage,
                'old_commit': old_commit, 'new_commit': new_commit,
                **{f'old_{field}': int(old.get(field) or 0) for field in FIELDS},
                **{f'new_{field}': int(new.get(field) or 0) for field in FIELDS},
            })

    write_csv(OUT / 'modern_publication_endpoints.csv', endpoints)
    write_csv(OUT / 'modern_publication_stage_ledger.csv', stages)
    evidence_files = [
        ROOT / 'data/rdh_2022_district_vote_audit.json',
        ROOT / 'data/rdh_2024_district_vote_audit.json',
        ROOT / 'data/benchmarks/pa_county_2022_us_senate_certified.csv',
        ROOT / 'data/benchmarks/pa_county_2024_president_certified.csv',
    ]
    fingerprints = {
        'commits': {
            commit: {'tree': git('rev-parse', f'{commit}^{{tree}}'), 'stage': stage}
            for sequence in SEQUENCES.values() for commit, stage in sequence
        },
        'historical_file_blobs': dict(sorted(file_blob_fingerprints.items())),
        'tracked_evidence': {
            path.relative_to(ROOT).as_posix(): digest(path) for path in evidence_files
        },
        'target_rows_lf_sha256': digest(target_path),
        'audit_script_lf_sha256': digest(Path(__file__)),
    }
    (OUT / 'modern_publication_input_fingerprints.json').write_text(
        json.dumps(fingerprints, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    summary = {
        'target_rows': len(targets),
        'endpoint_rows': len(endpoints),
        'directed_stage_rows': len(stages),
        'final_numeric_mismatches': 0,
        'candidate_names_preserved': True,
        'rows_by_year': {
            str(year): sum(int(row['year']) == year for row in targets) for year in sorted(SEQUENCES)
        },
        'classification': 'exact retained publication-history lineage; not independent geography or production approval',
        'production_changes': [],
    }
    (OUT / 'modern_publication_summary.json').write_text(
        json.dumps(summary, indent=2) + '\n', encoding='utf-8'
    )
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

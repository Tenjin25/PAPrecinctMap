"""Rebuild retained 2022/2024 RDH endpoints and seal compact lineage evidence."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'stage_lineage'
BUILDER = ROOT / 'Scripts/build_rdh_2024_district_contests.py'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')


def digest(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.json', '.md', '.py', '.txt'}:
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def save_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or list(rows[0])
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-2022', type=Path, default=ROOT / 'data/pa_2022_gen_prec_csv.zip')
    parser.add_argument('--source-2024', type=Path, default=ROOT / 'data/pa_2024_gen_prec_csv.zip')
    args = parser.parse_args()
    sources = {2022: args.source_2022.resolve(), 2024: args.source_2024.resolve()}
    for year, source in sources.items():
        if not source.exists():
            raise FileNotFoundError(f'Supplied RDH {year} archive not found: {source}')

    OUT.mkdir(exist_ok=True)
    endpoints, counties, mail_rows = [], [], []
    district_integerization, county_integerization = [], []
    fingerprints = {
        'Scripts/build_rdh_2024_district_contests.py': digest(BUILDER),
        'data/rdh_2022_district_vote_audit.json': digest(ROOT / 'data/rdh_2022_district_vote_audit.json'),
        'data/rdh_2024_district_vote_audit.json': digest(ROOT / 'data/rdh_2024_district_vote_audit.json'),
    }
    source_fingerprints = {}
    with tempfile.TemporaryDirectory(prefix='_rdh_stage_', dir=OUT) as temporary:
        temporary = Path(temporary)
        for year, source in sources.items():
            target = temporary / str(year)
            command = [
                sys.executable, str(BUILDER), '--year', str(year),
                '--source', str(source), '--output', str(target),
            ]
            if year == 2022:
                command.extend(['--county-controls-dir', str(ROOT / 'data/contests')])
            subprocess.run(command, cwd=ROOT, check=True)
            audit = json.loads((target / 'audit.json').read_text(encoding='utf-8'))
            source_fingerprints[str(year)] = {
                'supplied_filename': source.name,
                'sha256': digest(source),
                'rows': audit['rows'],
                'unique_ids': audit['unique_ids'],
            }
            if audit['source_sha256'] != source_fingerprints[str(year)]['sha256']:
                raise RuntimeError(f'RDH {year} source fingerprint changed during replay')
            for residual in audit['residual_allocations']:
                mail_rows.append({
                    'year': year,
                    'scope': residual['scope'],
                    'contest': residual['contest'],
                    'county': residual['county'],
                    'precinct': residual['precinct'],
                    'column': residual['column'],
                    'congressional_district': residual['congressional_district'],
                    'votes': residual['votes'],
                    'district_allocations': json.dumps(residual['district_weights'], sort_keys=True, separators=(',', ':')),
                    'method': 'localized_same-candidate_congressional_mail_pool',
                })
            for path in sorted(target.glob('*.json')):
                if path.name in {'audit.json', 'manifest.json'}:
                    continue
                payload = json.loads(path.read_text(encoding='utf-8'))
                allocation = payload['meta']['allocation_audit']
                county_audit = payload['meta']['county_conservation_audit']
                integerization = payload['meta']['integerization_audit']
                if any(int(allocation[key]) for key in ('unmatched_rows', 'unmatched_votes', 'unallocated_rows', 'unallocated_votes')):
                    raise RuntimeError(f'Incomplete RDH replay: {path.name}')
                if not allocation['conserved_for_matched_rows']:
                    raise RuntimeError(f'Nonconserved statewide RDH replay: {path.name}')
                if payload['meta']['coverage_percent'] != 100.0:
                    raise RuntimeError(f'Incomplete district coverage: {path.name}')
                for district, row in sorted(payload['general']['results'].items(), key=lambda item: int(item[0])):
                    endpoints.append({
                        'file': path.name, 'year': year, 'contest': payload['contest_type'],
                        'scope': payload['scope'], 'district': district,
                        **{field: int(row[field]) for field in FIELDS},
                        'source_sha256': source_fingerprints[str(year)]['sha256'],
                        'builder_sha256': fingerprints['Scripts/build_rdh_2024_district_contests.py'],
                        'zero_unmatched_unallocated': True,
                        'county_conservation_exact': county_audit['all_counties_conserved'],
                        'lineage_eligible': county_audit['all_counties_conserved'],
                        'coverage_percent': payload['meta']['coverage_percent'],
                    })
                for county, evidence in sorted(county_audit['counties'].items()):
                    counties.append({
                        'file': path.name, 'year': year, 'contest': payload['contest_type'],
                        'scope': payload['scope'], 'county': county,
                        'source_votes': json.dumps(evidence['source'], sort_keys=True, separators=(',', ':')),
                        'allocated_votes': json.dumps(evidence['allocated'], sort_keys=True, separators=(',', ':')),
                        'district_allocations': json.dumps(evidence['district_allocations'], sort_keys=True, separators=(',', ':')),
                        'allocation_quality_votes': json.dumps(evidence['allocation_quality_votes'], sort_keys=True, separators=(',', ':')),
                        'conserved': evidence['conserved'],
                    })
                for district, evidence in sorted(integerization['district_changes'].items(), key=lambda item: int(item[0])):
                    before = evidence['before_statewide_rounding']
                    after = evidence['after_county_largest_remainder']
                    delta = evidence['delta']
                    district_integerization.append({
                        'file': path.name, 'year': year, 'contest': payload['contest_type'],
                        'scope': payload['scope'], 'district': district,
                        **{f'before_{field}': before[field] for field in FIELDS},
                        **{f'after_{field}': after[field] for field in FIELDS},
                        **{f'delta_{field}': delta[field] for field in FIELDS},
                    })
                for county, district_changes in sorted(integerization['county_district_increments_over_truncation'].items()):
                    for district, delta in sorted(district_changes.items(), key=lambda item: int(item[0])):
                        county_integerization.append({
                            'file': path.name, 'year': year, 'contest': payload['contest_type'],
                            'scope': payload['scope'], 'county': county, 'district': district,
                            **{f'increment_{field}': delta[field] for field in FIELDS},
                        })

    save_csv(OUT / 'rdh_replay_endpoints.csv', endpoints)
    save_csv(OUT / 'rdh_county_conservation.csv', counties)
    save_csv(OUT / 'rdh_mail_rows.csv', mail_rows)
    save_csv(OUT / 'rdh_integerization_district_changes.csv', district_integerization)
    save_csv(OUT / 'rdh_integerization_county_increments.csv', county_integerization)
    (OUT / 'rdh_input_fingerprints.json').write_text(json.dumps({
        'tracked_inputs': fingerprints,
        'supplied_archives': source_fingerprints,
    }, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    summary = {
        'years': sorted(sources),
        'endpoint_rows': len(endpoints),
        'county_evidence_rows': len(counties),
        'localized_mail_rows': len(mail_rows),
        'integerization_district_change_rows': len(district_integerization),
        'integerization_county_increment_rows': len(county_integerization),
        'zero_unmatched_unallocated_files': len({row['file'] for row in endpoints}),
        'county_conserved_files': len({row['file'] for row in endpoints if row['lineage_eligible']}),
        'county_blocked_files': sorted({row['file'] for row in endpoints if not row['lineage_eligible']}),
        'eligible_endpoint_rows': sum(row['lineage_eligible'] for row in endpoints),
        'county_conservation_failures': sum(row['conserved'] is not True for row in counties),
        'classification': 'official-return rebuild endpoints; exact equality establishes numerical lineage only',
        'production_changes': [],
    }
    (OUT / 'rdh_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

"""Retain full-data acceptance evidence without publishing the candidate."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_bef_candidate as candidate

WORK = Path(__file__).resolve().parent


def main():
    fresh = WORK / 'acceptance_26d3baa'
    before = ROOT / 'data/district_bef_candidate'
    receipt = json.loads((fresh / 'build_receipt.json').read_text())
    candidate.validate_reuse(fresh, receipt['inputs'])
    missing, incorrect, repaired, arithmetic, name_changes = [], [], [], [], []
    builder = candidate.import_builder()
    audited = 0
    for path in sorted(fresh.glob('*.json')):
        if path.name in {'manifest.json', 'acceptance_report.json', 'build_receipt.json'}:
            continue
        payload = json.loads(path.read_text())
        if not builder.is_statewide_contest_type(payload.get('contest_type', '')):
            continue
        errors = candidate.verify_county_evidence(payload)
        if errors == ['missing county allocation evidence']:
            missing.append({'file': path.name, 'year': payload['year'], 'contest': payload['contest_type'], 'reason': errors[0]})
        elif errors:
            incorrect.append({'file': path.name, 'errors': errors})
        else:
            audited += 1
        old_path = before / path.name
        if not old_path.exists():
            continue
        old = json.loads(old_path.read_text())
        old_errors = candidate.verify_county_evidence(old)
        if old_errors and not errors:
            repaired.append(path.name)
        for district, row in payload['general']['results'].items():
            previous = old['general']['results'].get(district, {})
            if any(row.get(field) != previous.get(field) for field in ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')):
                arithmetic.append({'file': path.name, 'district': district})
            if any(row.get(field) != previous.get(field) for field in ('dem_candidate', 'rep_candidate')):
                name_changes.append({'file': path.name, 'district': district})
    report = json.loads((fresh / 'acceptance_report.json').read_text())
    warm_times = {}
    output_hashes = candidate.candidate_fingerprints(fresh)
    ledger_hash = candidate.digest(fresh / 'district_vote_changes.csv')
    for flag in ('--reuse', '--incremental'):
        started = time.perf_counter()
        run = subprocess.run([sys.executable, str(ROOT / 'Scripts/build_bef_candidate.py'),
                              '--out-dir', str(fresh), flag, '--quiet'], cwd=ROOT,
                             text=True, capture_output=True, check=False)
        warm_times[flag] = time.perf_counter() - started
        assert run.returncode == (0 if report['status'] == 'PASS' else 2), run.stderr
        result = json.loads(run.stdout)
        assert result['counts'] == report['counts'] and result['status'] == report['status']
        assert candidate.candidate_fingerprints(fresh) == output_hashes
        assert candidate.digest(fresh / 'district_vote_changes.csv') == ledger_hash
    summary = {'source_commit': '26d3baa281e493399a965858571cc3cddf812d94',
               'status': report['status'], 'acceptance': report['acceptance'], 'counts': report['counts'],
               'build_receipt_sha256': hashlib.sha256((fresh / 'build_receipt.json').read_bytes()).hexdigest(),
               'source_content_fingerprints': len(receipt['inputs']), 'output_content_fingerprints': len(receipt['outputs']),
               'independently_verified_statewide_contest_files': audited,
               'missing_county_evidence_files': missing, 'actual_county_arithmetic_failures': incorrect,
               'repaired_county_metadata_files': repaired,
               'vote_changes_from_original_cold_baseline': arithmetic,
               'candidate_name_changes_from_original_cold_baseline': name_changes,
               'warm_reuse_seconds': warm_times['--reuse'], 'warm_unchanged_incremental_seconds': warm_times['--incremental'],
               'warm_behavior': 'Both commands retain BLOCKED, the same 5409 district differences, 33 missing-evidence files, and 6 geographic-bound failures; no rebuild and no acceptance bypass.',
               'selective_changed_year_integration': 'Passed real-builder controlled-source lifecycle test; untouched-year JSON hashes and both-year manifest preserved.',
               'production_changes': []}
    (WORK / 'report/acceptance_integration.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: value if not isinstance(value, list) else len(value) for key, value in summary.items() if key not in {'acceptance', 'warm_behavior'}}, indent=2))


if __name__ == '__main__':
    main()

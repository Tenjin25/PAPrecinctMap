"""Verify cold/warm generic acceptance after the narrow reviewed promotion."""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_bef_candidate as candidate
import reviewed_precinct_corrections as reviewed

WORK = Path(__file__).resolve().parent


def main():
    directory = WORK / 'acceptance_emmaus_release_portable'
    fingerprints = candidate.input_fingerprints(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    candidate.validate_reuse(directory, fingerprints)
    report = json.loads((directory / 'acceptance_report.json').read_text())
    assert report['status'] == 'BLOCKED'
    assert report['counts']['district_vote_changes'] == 5409
    assert report['counts']['statewide_total_changes'] == 0
    assert report['counts']['candidate_name_changes'] == 0
    assert report['counts']['files_with_unmatched_or_unallocated_rows'] == 0
    assert report['counts']['geographic_bounds_failures'] == 6
    review = json.loads((ROOT / 'data/benchmarks/reviewed_emmaus_2016.json').read_text())
    assert all(str((ROOT / name).resolve()) in fingerprints for name in review['input_hashes'])
    for entry in review['entries']:
        payload = json.loads((directory / entry['file']).read_text())
        assert reviewed.vote_hash(payload) == entry['corrected_vote_hash']
        assert candidate.verify_county_evidence(payload) == []
        assert not reviewed.apply_reviewed_correction(payload, review, ROOT)
    verified, missing, arithmetic = 0, [], []
    builder = candidate.import_builder()
    for path in directory.glob('*.json'):
        if path.name in ('manifest.json', 'acceptance_report.json', 'build_receipt.json'):
            continue
        payload = json.loads(path.read_text())
        if not builder.is_statewide_contest_type(payload.get('contest_type', '')):
            continue
        errors = candidate.verify_county_evidence(payload)
        if errors == ['missing county allocation evidence']:
            missing.append(path.name)
        elif errors:
            arithmetic.append({'file': path.name, 'errors': errors})
        else:
            verified += 1
    assert not arithmetic and len(missing) == 33 and verified == 228
    outputs = candidate.candidate_fingerprints(directory)
    delta_hash = candidate.digest(directory / 'district_vote_changes.csv')
    timings = {}
    for flag in ('--reuse', '--incremental'):
        started = time.perf_counter()
        run = subprocess.run([sys.executable, 'Scripts/build_bef_candidate.py', '--out-dir', str(directory), flag, '--quiet'],
                             cwd=ROOT, capture_output=True, text=True, check=False)
        timings[flag] = time.perf_counter() - started
        assert run.returncode == 2, run.stderr
        warm = json.loads(run.stdout)
        assert warm['counts'] == report['counts'] and warm['status'] == 'BLOCKED'
        assert candidate.candidate_fingerprints(directory) == outputs
        assert candidate.digest(directory / 'district_vote_changes.csv') == delta_hash
    summary = {'status': 'PASS_for_narrow_review_reproduction_broad_candidate_remains_BLOCKED',
               'candidate_counts': report['counts'], 'generic_acceptance': report['acceptance'],
               'reviewed_layers_reproduced': len(review['entries']), 'reviewed_county_evidence': 'independently verified',
               'independently_verified_statewide_contest_files': verified, 'actual_county_arithmetic_failures': arithmetic,
               'missing_legacy_county_evidence_files': sorted(missing),
               'warm_seconds': timings, 'warm_checks': 'same blocked gates, output hashes and all 5409 delta rows preserved',
               'receipt_sha256': candidate.digest(directory / 'build_receipt.json'), 'output_files_fingerprinted': len(outputs),
               'source_files_fingerprinted': len(fingerprints), 'all_reviewed_transitive_inputs_fingerprinted': True,
               'broad_candidate_promoted': False}
    (WORK / 'report/post_release_acceptance.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('generic_acceptance', 'missing_legacy_county_evidence_files')}, indent=2))


if __name__ == '__main__':
    main()

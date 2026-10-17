"""Run the actual release checks and retain command results as diagnostics."""
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent


def main():
    commands = [
        ['Scripts/test_county_clustered_district_contests.py'],
        ['Scripts/test_bef_candidate_reuse.py'],
        ['Scripts/test_source_ledger.py'],
        ['Scripts/test_reviewed_precinct_corrections.py'],
        ['data/district_reconciliation_work/test_reconciliation_diagnostics.py'],
        ['data/district_reconciliation_work/test_acceptance_lifecycle.py'],
        ['Scripts/audit_district_vote_conservation.py', 'data/district_contests'],
        ['Scripts/audit_reviewed_precinct_corrections.py'],
        ['Scripts/candidate_name_normalizer.py', '--check', 'data/contests', 'data/district_contests', 'data/pa_elections_aggregated.json'],
    ]
    results = []
    for args in commands:
        print('Checking ' + ' '.join(args), flush=True)
        run = subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True, check=False)
        results.append({'command': 'python ' + ' '.join(args), 'exit_code': run.returncode,
                        'stdout': run.stdout.strip(), 'stderr': run.stderr.strip()})
        if run.returncode:
            raise RuntimeError(json.dumps(results[-1], indent=2))
    ledger = ROOT / 'data/source_ledger.json'
    before = hashlib.sha256(ledger.read_bytes()).hexdigest()
    run = subprocess.run([sys.executable, 'Scripts/build_source_ledger.py'], cwd=ROOT, capture_output=True, text=True, check=True)
    assert hashlib.sha256(ledger.read_bytes()).hexdigest() == before, 'Source ledger was stale'
    results.append({'command': 'python Scripts/build_source_ledger.py; compare output hash', 'exit_code': 0, 'stdout': run.stdout.strip()})
    with (WORK / 'emmaus_review/proposed_district_changes.csv').open(newline='') as handle:
        proposals = list(csv.DictReader(handle))
    grouped = {}
    for row in proposals:
        grouped.setdefault(row['file'], []).append(row)
    for filename, rows in grouped.items():
        before = json.loads(subprocess.run(['git', 'show', f'26d3baa:data/district_contests/{filename}'], cwd=ROOT, check=True, text=True, capture_output=True).stdout)
        after = json.loads((ROOT / 'data/district_contests' / filename).read_text())
        changed = {d for d in before['general']['results'] if any(before['general']['results'][d][f] != after['general']['results'][d][f]
                    for f in ('dem_votes', 'rep_votes', 'other_votes', 'total_votes'))}
        assert changed == {row['district'] for row in rows} == {'131', '134'}
        for row in rows:
            for field in ('dem_votes', 'rep_votes', 'other_votes', 'total_votes'):
                assert before['general']['results'][row['district']][field] == int(row[f'before_{field}'])
                assert after['general']['results'][row['district']][field] == int(row[f'after_{field}'])
    touched = subprocess.run(['git', 'diff', '--name-only', '26d3baa', '--', 'data/district_contests'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()
    assert set(touched) == {f'data/district_contests/{name}' for name in grouped}
    subprocess.run(['git', 'diff', '--exit-code', '26d3baa', '--', 'data/contests', 'data/pa_elections_aggregated.json'], cwd=ROOT, check=True)
    report = {'status': 'PASS', 'baseline_commit': '26d3baa281e493399a965858571cc3cddf812d94',
              'tests_passed': sum(int(n) for r in results for n in re.findall(r'Ran (\d+) tests? in', r.get('stderr', '') + '\n' + r.get('stdout', ''))),
              'commands': results, 'production_changed_files': sorted(grouped),
              'production_changed_district_rows': len(proposals), 'all_other_production_vote_files_unchanged': True,
              'cachebuster': '2026-10-16-emmaus-precinct-v13', 'broad_candidate_promoted': False}
    (WORK / 'report/production_validation.json').write_text(json.dumps(report, indent=2) + '\n')
    release = json.loads((WORK / 'emmaus_release/release_report.json').read_text())
    (WORK / 'report/reviewed_release.json').write_text(json.dumps(release, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'commands'}, indent=2))


if __name__ == '__main__':
    main()

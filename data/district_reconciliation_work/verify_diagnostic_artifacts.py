"""Create/check the allowlisted, portable diagnostic artifact checksums.

No private archives, duplicate downloads, full candidate directories, or large
transient raw-source ledgers are part of this release manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path

WORK = Path(__file__).resolve().parent
FOLDERS = ('original_block_years', 'pa10_original_blocks', 'pa10_raw_returns',
           'benchmark_counties_all_scopes_2018', 'priority_counties_raw_years',
           'lehigh_2016', 'hd134_legal_membership', 'hybrid_review',
           'reverse_crosswalk_exposure', 'reverse_crosswalk_candidate',
           'stage_lineage', 'judicial_evidence', 'emmaus_review',
           'certification_stages_2018', 'report')


def checksum(path):
    content = path.read_bytes()
    if path.suffix == '.json':
        content = json.dumps(json.loads(content.decode('utf-8-sig')), sort_keys=True, separators=(',', ':')).encode()
    elif path.suffix in ('.csv', '.txt', '.py', '.md'):
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def release_files():
    paths = list(WORK.glob('*.py')) + [WORK / 'ALLOCATION_DECISION.md', WORK / 'BATCH_PLAN.md']
    for folder in FOLDERS:
        paths.extend(p for p in (WORK / folder).iterdir() if p.is_file()
                     and p.name != 'official_download.txt'
                     and not (folder == 'priority_counties_raw_years' and p.name.endswith('_source_allocations.csv')))
    return sorted(paths)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    manifest = WORK / 'diagnostic_artifacts.json'
    if args.write:
        payload = {'representation': 'JSON: sorted compact serialization; CSV/TXT/PY/MD: CRLF to LF; all other bytes exact.',
                   'files': {p.relative_to(WORK).as_posix(): checksum(p) for p in release_files()}}
        manifest.write_text(json.dumps(payload, indent=2) + '\n')
    payload = json.loads(manifest.read_text())
    for name, expected in payload['files'].items():
        path = (WORK / name).resolve()
        if not path.is_relative_to(WORK.resolve()) or checksum(path) != expected:
            raise ValueError(f'Diagnostic artifact missing or changed: {name}')
    print(f'Diagnostic artifact checks passed: {len(payload["files"])} portable fingerprints.')


if __name__ == '__main__':
    main()

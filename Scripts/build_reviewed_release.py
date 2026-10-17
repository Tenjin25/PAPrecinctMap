"""Build, validate, and explicitly promote only the source-bound Emmaus review.

The broad generic candidate remains blocked. This release preserves every
unreviewed published file byte-for-byte and changes only the approved rows.
"""
import argparse
import csv
import hashlib
import json
import os
import shutil
from pathlib import Path

import reviewed_precinct_corrections as reviewed

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / 'data/district_contests'
REVIEW = ROOT / 'data/benchmarks/reviewed_emmaus_2016.json'


def hashes(directory):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(directory.glob('*.json'))}


def validate_pair(before, after, entry, review):
    if reviewed.vote_hash(before) != entry['baseline_vote_hash'] or reviewed.vote_hash(after) != entry['corrected_vote_hash']:
        raise ValueError('Review does not match the baseline and proposed output')
    expected = json.loads(json.dumps(before))
    reviewed.apply_reviewed_correction(expected, review, ROOT)
    if expected != after:
        raise ValueError('Unexpected candidate fields outside the reviewed correction')
    reviewed.verify_counties(after, after['meta']['county_conservation_audit'])
    with (ROOT / f'data/benchmarks/pa_county_2016_{entry["contest_type"]}_certified.csv').open(newline='', encoding='utf-8-sig') as handle:
        controls = {row['county'].upper(): {f: int(row[f]) for f in reviewed.FIELDS[:3]} for row in csv.DictReader(handle)}
    counties = after['meta']['county_conservation_audit']['counties']
    if set(counties) != set(controls):
        raise ValueError('County evidence coverage differs from the certified controls')
    for county, values in controls.items():
        if any(counties[county]['source'][f] != n for f, n in values.items()):
            raise ValueError(f'County evidence differs from certified returns: {county}')
    changed = []
    for district, row in after['general']['results'].items():
        old = before['general']['results'][district]
        if any(row[f] != old[f] for f in reviewed.FIELDS):
            changed.append(district)
        if any(row[f] != old[f] for f in ('dem_candidate', 'rep_candidate')):
            raise ValueError('Candidate names must survive verbatim')
    if set(changed) != {'131', '134'}:
        raise ValueError('Unexpected changed district set')
    for field in reviewed.FIELDS:
        if sum(r[field] for r in before['general']['results'].values()) != sum(r[field] for r in after['general']['results'].values()):
            raise ValueError('Statewide party conservation failure')
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--reuse', action='store_true')
    parser.add_argument('--promote', action='store_true', help='Explicitly replace only the five reviewed production files after all checks')
    args = parser.parse_args()
    out = args.out_dir.resolve()
    if out == PUBLISHED.resolve() or PUBLISHED.resolve() in out.parents or out in PUBLISHED.resolve().parents:
        raise ValueError('Release candidate must be isolated from production')
    review = json.loads(REVIEW.read_text())
    entries = {entry['file']: entry for entry in review['entries']}
    receipt_path = out.parent / 'release_receipt.json'
    baseline = hashes(PUBLISHED)
    if args.reuse:
        receipt = json.loads(receipt_path.read_text())
        if receipt['baseline_files'] != baseline or receipt['candidate_files'] != hashes(out) or receipt['review_hash'] != reviewed.canonical_hash(review):
            raise ValueError('Release inputs or outputs changed; new isolated build required')
    else:
        if out.exists() or receipt_path.exists():
            raise ValueError('Refusing to overwrite an existing release candidate; use --reuse or a new directory')
        out.mkdir(parents=True)
        for path in PUBLISHED.glob('*.json'):
            shutil.copy2(path, out / path.name)
        for filename, entry in entries.items():
            payload = json.loads((out / filename).read_text())
            reviewed.apply_reviewed_correction(payload, review, ROOT)
            (out / filename).write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
        receipt = {'review_hash': reviewed.canonical_hash(review), 'baseline_files': baseline, 'candidate_files': hashes(out)}
    candidate_hashes = hashes(out)
    if set(candidate_hashes) != set(baseline):
        raise ValueError('Release file coverage changed')
    changed = []
    for filename in baseline:
        if filename not in entries:
            if candidate_hashes[filename] != baseline[filename]:
                raise ValueError(f'Unreviewed file changed: {filename}')
            continue
        before, after = (json.loads(path.read_text()) for path in (PUBLISHED / filename, out / filename))
        changed.extend({'file': filename, 'district': d} for d in validate_pair(before, after, entries[filename], review))
    if hashes(PUBLISHED) != baseline:
        raise ValueError('Production changed during release validation')
    if hashes(out) != candidate_hashes:
        raise ValueError('Candidate changed during release validation')
    report = {'status': 'PASS', 'release_scope': review['id'], 'changed_files': sorted(entries), 'changed_district_rows': changed,
              'county_party_conservation': 'exact_against_all_67_certified_counties', 'statewide_party_conservation': 'exact',
              'unmatched_or_unallocated_source_rows': 0, 'candidate_names': 'preserved_verbatim',
              'unreviewed_files': 'byte_identical', 'broad_candidate': 'BLOCKED_not_promoted',
              'promoted': False}
    receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
    if args.promote:
        # All preflights complete before the first replacement. Retain originals
        # and roll back every replacement if any filesystem operation fails.
        originals = {name: (PUBLISHED / name).read_bytes() for name in entries}
        backup = out.parent / 'before'
        backup.mkdir(exist_ok=True)
        for name, content in originals.items():
            (backup / name).write_bytes(content)
        try:
            for name in entries:
                temporary = PUBLISHED / (name + '.reviewed.tmp')
                temporary.write_bytes((out / name).read_bytes())
                os.replace(temporary, PUBLISHED / name)
            if hashes(PUBLISHED) != receipt['candidate_files']:
                raise ValueError('Post-promotion output verification failed')
        except Exception:
            for name, content in originals.items():
                (PUBLISHED / name).write_bytes(content)
            raise
        report['promoted'] = True
    (out.parent / 'release_report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

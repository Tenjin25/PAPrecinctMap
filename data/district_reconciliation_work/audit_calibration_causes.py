"""Recognize complete, numerically verified calibration causes, not guesses."""
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')


def main():
    certification = {}
    directory = WORK / 'certification_stages_2018'
    if directory.exists():
        replay = json.loads((directory / 'westmoreland_replay_summary.json').read_text())
        assert replay['unmatched_rows'] == 0
        exact_models = {'controlled_integerized_rows', 'uncontrolled_integerized_rows'}
        checks = [r for r in replay['variant_results'] if r['model'] in exact_models]
        assert len(checks) == 6 and all(r['district_party_mismatches'] == 0 for r in checks)
        with (directory / 'district_party_stage_ledger.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                assert int(row['published_reproduction_delta']) == 0
                certification.setdefault((f"{row['scope']}_us_senate_2018.json", row['district']), {})[row['party_bucket'] + '_votes'] = row
    stages = {}
    for path in sorted((ROOT / 'data/district_bef_audit').glob('dra_*_changes.csv')):
        match = re.fullmatch(r'dra_(congressional|state_house|state_senate)_(.+)_(\d{4})_changes', path.stem)
        if path.name == 'dra_2018_us_senate_congressional_changes.csv':
            scope, contest, year = 'congressional', 'us_senate', 2018
        elif match:
            scope, contest, year = match[1], match[2], int(match[3])
        else:
            continue
        with path.open(newline='') as handle:
            for row in csv.DictReader(handle):
                values = {}
                for prefix in ('old', 'new'):
                    values[prefix] = {field: int(row.get(f'{prefix}_{field}', row.get(f'{prefix}_{field.removesuffix("_votes")}'))) for field in FIELDS}
                stages[(f'{scope}_{contest}_{year}.json', row['district'])] = (
                    values, path.relative_to(ROOT).as_posix(),
                    hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest())
    output, counts, groups = [], Counter(), Counter()
    with (ROOT / 'data/district_bef_candidate/district_vote_changes.csv').open(newline='') as handle:
        for change in csv.DictReader(handle):
            key = change['file'], change['district']
            stage = stages.get(key)
            old_matches = new_matches = False
            if stage:
                old_matches = all(int(change[f'candidate_{field}']) == stage[0]['old'][field] for field in FIELDS)
                new_matches = all(int(change[f'published_{field}']) == stage[0]['new'][field] for field in FIELDS)
            status = 'fully_explained_calibration' if old_matches and new_matches else 'calibration_stage_present_other_causes_unresolved' if stage else 'unresolved_no_exact_stage_evidence'
            certified = certification.get(key)
            certification_matches = bool(certified) and all(
                int(change[f'candidate_{field}']) == int(certified[field]['generic_candidate']) and
                int(change[f'published_{field}']) == int(certified[field]['published'])
                for field in FIELDS[:3])
            if certification_matches and status != 'fully_explained_calibration':
                status = 'fully_explained_calibration_and_certification_order'
            counts[status] += 1
            scope = 'state_house' if key[0].startswith('state_house_') else 'state_senate' if key[0].startswith('state_senate_') else 'congressional'
            year = int(key[0][-9:-5])
            contest = key[0][len(scope) + 1:-10]
            cause = 'legacy DRA calibration' if old_matches and new_matches else 'unresolved'
            if status == 'fully_explained_calibration_and_certification_order':
                cause = 'legacy DRA calibration plus localized county certification allocation order'
            county = ('129/Westmoreland (certification only; DRA county components unavailable)'
                      if status == 'fully_explained_calibration_and_certification_order'
                      else 'not attributable from district calibration')
            groups[(year, contest, scope, county, cause, status)] += 1
            row = {'file': key[0], 'year': year, 'contest': contest, 'scope': scope,
                   'district': key[1], 'status': status,
                   'cause': cause,
                   'candidate_equals_precalibration': old_matches, 'published_equals_postcalibration': new_matches,
                   'evidence': stage[1] if stage else '',
                   'evidence_lf_sha256': stage[2] if stage else '',
                   'county_cause_attribution': 'not available in calibration source; do not distribute district deltas among counties'}
            for field in FIELDS:
                observed = int(change[f'candidate_{field}']) - int(change[f'published_{field}'])
                calibration = stage[0]['old'][field] - stage[0]['new'][field] if stage else 0
                row[f'observed_{field}_delta'] = observed
                row[f'calibration_{field}_delta'] = calibration if stage else ''
                row[f'certification_order_{field}_delta'] = (
                    sum(int(certified[f]['non_dra_stage_difference']) for f in FIELDS[:3])
                    if field == 'total_votes' else int(certified[field]['non_dra_stage_difference'])
                ) if certification_matches else 0
                row[f'unresolved_{field}_delta'] = observed - calibration if stage else observed
            if status == 'fully_explained_calibration_and_certification_order':
                row['evidence'] += '; data/district_reconciliation_work/certification_stages_2018/'
                row['county_cause_attribution'] = '129/Westmoreland: certification component independently replayed; DRA county components unavailable'
                for field in FIELDS:
                    row[f'unresolved_{field}_delta'] = 0
            output.append(row)
    path = WORK / 'report/verified_calibration_causes.csv'
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    (WORK / 'report/calibration_cause_counts.json').write_text(json.dumps(dict(counts), indent=2) + '\n')
    with (WORK / 'report/verified_cause_groups.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.writer(handle)
        writer.writerow(['year', 'contest', 'scope', 'county', 'cause', 'status', 'district_rows'])
        writer.writerows([*key, count] for key, count in sorted(groups.items()))
    print(json.dumps(dict(counts), indent=2))


if __name__ == '__main__':
    main()

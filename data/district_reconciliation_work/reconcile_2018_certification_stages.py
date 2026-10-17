"""Reconcile retained DRA and localized Westmoreland certification stages.

This is lineage evidence, not independent validation of DRA geography. Never
infer county components for a calibrated district residual.
"""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'certification_stages_2018'
SOURCES = {
    'congressional': 'dra_2018_us_senate_congressional_changes.csv',
    'state_house': 'dra_state_house_us_senate_2018_changes.csv',
    'state_senate': 'dra_state_senate_us_senate_2018_changes.csv',
}
FIELDS = ('dem', 'rep', 'other')


def read(path):
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    delta_rows = read(ROOT / 'data/benchmarks/pa_county_2018_us_senate_district_deltas.csv')
    localized = {(r['scope'], r['district'], r['bucket']): int(r['district_delta']) for r in delta_rows}
    ledger, publication_mismatches, controls, residuals = [], [], [], []
    for scope, filename in SOURCES.items():
        current = json.loads((ROOT / f'data/district_contests/{scope}_us_senate_2018.json').read_text())
        candidate = json.loads((ROOT / f'data/district_bef_candidate/{scope}_us_senate_2018.json').read_text())
        pub, rebuilt = current['general']['results'], candidate['general']['results']
        stage = {r['district']: r for r in read(ROOT / 'data/district_bef_audit' / filename)}
        assert set(stage) == set(pub) == set(rebuilt)
        for district, row in stage.items():
            for field in FIELDS:
                before = int(row.get(f'old_{field}', row.get(f'old_{field}_votes')))
                after = int(row.get(f'new_{field}', row.get(f'new_{field}_votes')))
                production, exact = pub[district][field + '_votes'], rebuilt[district][field + '_votes']
                local_delta = localized.get((scope, district, field), 0)
                reproduction_delta = production - (after + local_delta)
                if reproduction_delta:
                    publication_mismatches.append({'scope': scope, 'district': district, 'party': field, 'delta': reproduction_delta})
                value = {'year': 2018, 'contest': 'us_senate', 'scope': scope, 'district': district, 'party_bucket': field,
                         'retained_pre_dra': before, 'retained_post_dra': after,
                         'dra_delta': after - before, 'localized_certification_delta': local_delta,
                         'reproduced_published': after + local_delta, 'published': production,
                         'generic_candidate': exact, 'generic_minus_pre_dra': exact - before,
                         'candidate_minus_published': exact - production,
                         'non_dra_stage_difference': exact - before - local_delta,
                         'published_reproduction_delta': reproduction_delta,
                         'county_attribution': '129/Westmoreland for certification deltas only; DRA county components unavailable',
                         'status': 'stage_lineage_only_not_promotion_evidence'}
                assert value['candidate_minus_published'] == -value['dra_delta'] + value['non_dra_stage_difference'] - reproduction_delta
                ledger.append(value)
                if value['non_dra_stage_difference']:
                    residuals.append(value)
        for field in FIELDS:
            selected = [r for r in ledger if r['scope'] == scope and r['party_bucket'] == field]
            controls.append({'scope': scope, 'party_bucket': field,
                             'generic_minus_pre_dra': sum(r['generic_minus_pre_dra'] for r in selected),
                             'localized_certification_delta': sum(r['localized_certification_delta'] for r in selected),
                             'non_dra_stage_difference': sum(r['non_dra_stage_difference'] for r in selected)})
    save('district_party_stage_ledger.csv', ledger)
    save('publication_reproduction_failures.csv', publication_mismatches)
    save('non_dra_stage_differences.csv', residuals)
    save('scope_party_stage_conservation.csv', controls)
    summary = {'district_rows': len({(r['scope'], r['district']) for r in ledger}),
               'published_stage_reproduction_failures': len(publication_mismatches),
               'non_dra_difference_district_rows': len({(r['scope'], r['district']) for r in residuals}),
               'non_dra_difference_party_rows': len(residuals), 'scope_party_controls': controls,
               'next_gate': 'Independently replay pre-certification allocation; a numeric stage identity alone does not prove the residual cause.',
               'production_changes': []}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

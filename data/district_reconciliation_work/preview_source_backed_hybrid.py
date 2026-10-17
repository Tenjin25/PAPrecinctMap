"""Preview conserved county-slice substitutions; never edit production."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'hybrid_review'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


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
    controls = defaultdict(dict)
    for row in read(WORK / 'priority_counties_raw_years/official_source_vs_certified_county_controls.csv'):
        controls[(int(row['year']), row['countyfp'], row['contest'])][row['party_bucket']] = row
    # County names from the official benchmark files, never guessed from district labels.
    names = {}
    for path in sorted((ROOT / 'data/benchmarks').glob('pa_county_*_certified.csv')):
        for row in read(path):
            if row.get('countyfp'):
                names[row['countyfp'].zfill(3)] = row['county'].upper()
    names.update({'041': 'CUMBERLAND', '043': 'DAUPHIN', '133': 'YORK', '077': 'LEHIGH', '045': 'DELAWARE', '101': 'PHILADELPHIA'})
    slices, transfers, preview, audits = [], [], [], []
    for year in (2016, 2018, 2020):
        unmatched = defaultdict(int)
        for row in read(WORK / f'priority_counties_raw_years/{year}_unmatched.csv'):
            unmatched[(row['scope'], row['countyfp'], row['contest'])] += 1
        direct = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(FIELDS, 0)))
        for row in read(WORK / f'priority_counties_raw_years/{year}_county_district_votes.csv'):
            direct[(row['scope'], row['countyfp'], row['contest'])][row['district']][row['party_bucket']] += int(row['votes'])
        by_file = defaultdict(list)
        for (scope, fp, contest), districts in sorted(direct.items()):
            filename = f'{scope}_{contest}_{year}.json'
            published = json.loads((ROOT / 'data/district_contests' / filename).read_text())
            candidate = json.loads((ROOT / 'data/district_bef_candidate' / filename).read_text())
            pub, cand = published['general']['results'], candidate['general']['results']
            equal = set(pub) == set(cand) and all(pub[d][f] == cand[d][f] for d in pub for f in FIELDS)
            before = candidate['meta']['county_conservation_audit']['counties'][names[fp]]['district_allocations']
            control = controls[(year, fp, contest)]
            controls_ok = set(control) == set(FIELDS) and all(int(r['source_minus_certified']) == 0 for r in control.values())
            conserved = all(sum(v[f] for v in before.values()) == sum(v[f] for v in districts.values()) == int(control[f]['certified_county_votes'])
                            for f in FIELDS) if controls_ok else False
            ready = equal and controls_ok and conserved and unmatched[(scope, fp, contest)] == 0
            slices.append({'year': year, 'contest': contest, 'scope': scope, 'countyfp': fp, 'county': names[fp],
                           'baseline_reproduces_all_published_districts': equal, 'source_controls_exact': controls_ok,
                           'unmatched_rows': unmatched[(scope, fp, contest)], 'county_party_conservation_exact': conserved,
                           'status': 'conserved_preview_geographic_review_required' if ready else 'blocked_do_not_substitute'})
            if not ready:
                continue
            by_file[filename].append((fp, before, districts))
            for district in sorted(set(before) | set(districts), key=int):
                for field in FIELDS:
                    old, new = before.get(district, {}).get(field, 0), districts.get(district, {}).get(field, 0)
                    transfers.append({'year': year, 'contest': contest, 'scope': scope, 'county': names[fp], 'district': district,
                                      'party_bucket': field, 'baseline_county_votes': old, 'original_precinct_county_votes': new,
                                      'delta': new - old, 'status': 'diagnostic_not_approved_for_promotion'})
        for filename, substitutions in sorted(by_file.items()):
            pub = json.loads((ROOT / 'data/district_contests' / filename).read_text())['general']['results']
            delta = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
            for fp, before, after in substitutions:
                for district in set(before) | set(after):
                    for field in FIELDS:
                        delta[district][field] += after.get(district, {}).get(field, 0) - before.get(district, {}).get(field, 0)
            assert all(sum(v[f] for v in delta.values()) == 0 for f in FIELDS)
            for district, values in sorted(delta.items(), key=lambda item: int(item[0])):
                if not any(values.values()):
                    continue
                assert district in pub
                row = {'file': filename, 'district': district, 'substituted_counties': '|'.join(names[fp] for fp, _, _ in substitutions),
                       'status': 'diagnostic_not_approved_for_promotion'}
                for field in FIELDS:
                    row[f'published_{field}'] = pub[district][field]
                    row[f'preview_{field}'] = pub[district][field] + values[field]
                    row[f'delta_{field}'] = values[field]
                    assert row[f'preview_{field}'] >= 0
                preview.append(row)
            audits.append({'file': filename, 'substituted_county_slices': len(substitutions),
                           'statewide_party_delta': json.dumps({f: sum(v[f] for v in delta.values()) for f in FIELDS}),
                           'candidate_names': 'published_names_preserved_no_production_write'})
    save('county_slice_review.csv', slices)
    save('county_district_party_transfers.csv', transfers)
    save('district_change_preview.csv', preview)
    save('conservation_audit.csv', audits)
    summary = {'county_slices_reviewed': len(slices), 'conserved_preview_county_slices': sum(r['status'].startswith('conserved') for r in slices),
               'preview_layers': len(audits), 'changed_district_rows': len(preview), 'production_changes': [],
               'decision': 'No promotion: source geography still needs independent review. Never apply pre-calibration deltas to calibrated publication.'}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

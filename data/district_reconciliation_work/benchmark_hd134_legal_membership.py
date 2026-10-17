"""Independent HD-134 membership benchmark from official district description.

No allocation weights or outcome targets are used. Historical ward/division
label continuity still needs review; these are diagnostic benchmarks only.
"""
import csv
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'hd134_legal_membership'
SOURCE = 'https://www.pa.gov/agencies/vote/resources/redistricting/pennsylvania-redistricting-house-of-representative'
OFFICES = {'USP': 'president', 'USS': 'us_senate', 'GOV': 'governor', 'ATT': 'attorney_general', 'AUD': 'auditor', 'TRE': 'treasurer'}
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def membership(label, municipality_type):
    # School subrows remain separate vote rows but share the named ward/division.
    label = re.sub(r'\s+School District \d+$', '', label).strip()
    if municipality_type == '6' and re.fullmatch(r'EMMAUS(?: D \d+)?', label):
        return True
    match = re.fullmatch(r'SALISBURY W (\d+)(?: D (\d+))?', label)
    if municipality_type == '4' and match:
        return int(match[1]) in (4, 5)
    match = re.fullmatch(r'ALLENTOWN W (\d+)(?: D (\d+))?', label)
    if municipality_type == '2' and match:
        ward, division = int(match[1]), int(match[2] or 0)
        if ward in (2, 3, 12, 16, 19):
            return True
        if ward in (11, 13):
            if not division:
                raise ValueError(f'Undivided label for a partially included ward: {label}')
            return division in ((1, 3) if ward == 11 else (1, 2, 3))
        return False
    if label.startswith(('EMMAUS', 'SALISBURY', 'ALLENTOWN')):
        raise ValueError(f'Unrecognized relevant municipality/precinct: {municipality_type} {label}')
    return False


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    controls = {}
    with (WORK / 'priority_counties_raw_years/official_source_vs_certified_county_controls.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['countyfp'] == '077':
                controls[(int(row['year']), row['contest'], row['party_bucket'])] = int(row['certified_county_votes'])
    ledger, comparisons = [], []
    for year in (2016, 2018, 2020):
        county, district, labels = defaultdict(int), defaultdict(int), set()
        with (ROOT / f'data/ElectionReturns_{year}_General_PrecinctReturns.txt').open(newline='', encoding='utf-8-sig') as handle:
            for line, parts in enumerate(csv.reader(handle), 1):
                if len(parts) < 29 or parts[8] not in OFFICES:
                    continue
                wide = len(parts) >= 35
                if parts[29 if wide else 27].zfill(3) != '077':
                    continue
                candidate = ' '.join(parts[11:15]).upper().strip()
                if not candidate or any(t in candidate for t in ('CAST VOTES', 'OVER VOTES', 'UNDER VOTES', 'TOTAL VOTES', 'WRITE-IN', 'WRITE IN')):
                    continue
                contest, party = OFFICES[parts[8]], parts[9]
                field = 'dem_votes' if party == 'DEM' else 'rep_votes' if party == 'REP' else 'other_votes'
                votes = int(parts[15])
                county[(contest, field)] += votes
                label = parts[22] if wide else ' '.join(p for p in parts[20:25] if p).strip()
                kind = parts[21 if wide else 19]
                if membership(label, kind):
                    district[(contest, field)] += votes
                    labels.add(label)
                    ledger.append({'year': year, 'source_line': line, 'contest': contest, 'precinct': label,
                                   'municipality_type': kind, 'candidate': candidate, 'party_bucket': field,
                                   'votes': votes, 'district': 134, 'basis': 'official_current_district_municipality_ward_division_description'})
        for contest in sorted({key[0] for key in district}):
            pub = json.loads((ROOT / f'data/district_contests/state_house_{contest}_{year}.json').read_text())['general']['results']['134']
            row = {'year': year, 'contest': contest, 'scope': 'state_house', 'district': 134,
                   'county_source_controls_exact': all(county[(contest, f)] == controls[(year, contest, f)] for f in FIELDS),
                   'status': 'historical_label_continuity_review_required_not_approved'}
            for field in FIELDS:
                row[f'legal_membership_{field}'] = district[(contest, field)]
                row[f'published_{field}'] = pub[field]
                row[f'delta_{field}'] = district[(contest, field)] - pub[field]
            total = sum(district[(contest, f)] for f in FIELDS)
            row['legal_membership_total'] = total
            row['dem_minus_rep_margin_pct'] = 100 * (district[(contest, 'dem_votes')] - district[(contest, 'rep_votes')]) / total
            comparisons.append(row)
    save('official_source_membership_ledger.csv', ledger)
    save('benchmark_comparison.csv', comparisons)
    (OUT / 'evidence.json').write_text(json.dumps({'source_url': SOURCE, 'district': 134, 'reviewed_date': '2026-10-16',
        'structured_membership': {'Emmaus_borough': 'whole', 'Salisbury_township_wards': [4, 5],
                                 'Allentown_whole_wards': [2, 3, 12, 16, 19], 'Allentown_partial_wards': {'11': [1, 3], '13': [1, 2, 3]}},
        'production_changes': [], 'limitation': 'Current official description; historical precinct boundary/label continuity must be checked before promotion.'}, indent=2) + '\n')
    print(json.dumps(comparisons, indent=2))


if __name__ == '__main__':
    main()

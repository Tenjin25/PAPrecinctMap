"""Assess completeness and certified controls before interpreting priority rows."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_county_clustered_2024_district_contests as clustered

OUT = Path(__file__).resolve().parent / 'priority_counties_raw_years'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    names = layers.county_fips_by_name()
    district_counties = defaultdict(set)
    for scope, values in clustered.load_district_assignments().items():
        for block, district in values.items():
            district_counties[(scope, district)].add(block[2:5])
    checks, target_rows = [], []
    for year in (2016, 2018, 2020):
        source_rows, allocated, unmatched = {}, defaultdict(int), defaultdict(list)
        with (OUT / f'{year}_source_allocations.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                source_rows[row['source_line']] = row
                for district, amount in json.loads(row['district_vote_allocations']).items():
                    allocated[(row['scope'], row['countyfp'], row['contest'], district, row['party_bucket'])] += amount
        with (OUT / f'{year}_unmatched.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                source_rows[row['source_line']] = row
                unmatched[(row['scope'], row['countyfp'], row['contest'])].append(row)
        source = defaultdict(int)
        for row in source_rows.values():
            source[(row['countyfp'], row['contest'], row['party_bucket'])] += int(row['source_votes'])
        for fp, contest in {(fp, contest) for fp, contest, field in source}:
            for field in FIELDS:
                source.setdefault((fp, contest, field), 0)
        certified = {}
        for path in (ROOT / 'data/benchmarks').glob(f'pa_county_{year}_*_certified.csv'):
            contest = path.stem[len(f'pa_county_{year}_'):-len('_certified')]
            with path.open(newline='') as handle:
                for row in csv.DictReader(handle):
                    fp = names[layers.normalize_county_name(row['county'])]
                    for field in FIELDS:
                        certified[(fp, contest, field)] = int(row[field])
        for (fp, contest, field), votes in sorted(source.items()):
            expected = certified.get((fp, contest, field))
            checks.append({'year': year, 'countyfp': fp, 'contest': contest, 'party_bucket': field,
                           'official_precinct_source_votes': votes, 'certified_county_votes': expected,
                           'source_minus_certified': votes - expected if expected is not None else '',
                           'source_control_status': 'match' if votes == expected else 'not_verified_do_not_promote'})
        for scope, district in [('congressional', '10'), ('state_house', '134'), ('state_house', '95'), ('state_house', '191'), ('state_senate', '1')]:
            counties = district_counties[(scope, district)]
            for contest in sorted({contest for fp, contest, field in source}):
                missing = sum(len(unmatched[(scope, fp, contest)]) for fp in counties)
                missing_votes = sum(int(row['source_votes']) for fp in counties for row in unmatched[(scope, fp, contest)])
                controls_match = all(source.get((fp, contest, field)) == certified.get((fp, contest, field)) and (fp, contest, field) in source for fp in counties for field in FIELDS)
                complete = controls_match and missing == 0
                path = ROOT / f'data/district_contests/{scope}_{contest}_{year}.json'
                if not path.exists():
                    continue
                published = json.loads(path.read_text())['general']['results'][district]
                item = {'year': year, 'contest': contest, 'scope': scope, 'district': district,
                        'district_counties': '|'.join(sorted(counties)), 'unmatched_scope_rows_in_own_counties': missing,
                        'unmatched_scope_votes_in_own_counties': missing_votes,
                        'all_own_counties_match_certified_source_controls': controls_match,
                        'status': 'source_complete_diagnostic_requiring_geographic_review' if complete else 'partial_or_source_control_mismatch_do_not_promote'}
                for field in FIELDS:
                    votes = sum(allocated[(scope, fp, contest, district, field)] for fp in counties)
                    item[f'raw_original_blocks_{field}'] = votes
                    item[f'published_{field}'] = published[field]
                    item[f'diagnostic_minus_published_{field}'] = votes - published[field]
                total = sum(item[f'raw_original_blocks_{field}'] for field in FIELDS)
                item['raw_original_blocks_total'] = total
                item['diagnostic_signed_margin_pct'] = 100 * (item['raw_original_blocks_dem_votes'] - item['raw_original_blocks_rep_votes']) / total if total else 0
                target_rows.append(item)
    save('official_source_vs_certified_county_controls.csv', checks)
    save('priority_district_source_completeness.csv', target_rows)
    summary = {'source_control_comparisons': len(checks), 'source_control_mismatches': sum(row['source_control_status'] != 'match' for row in checks),
               'target_district_year_contest_rows': len(target_rows),
               'source_complete_target_rows': sum(row['status'].startswith('source_complete') for row in target_rows),
               'production_changes': [], 'warning': 'Do not read partial-row totals as a complete district result.'}
    (OUT / 'review_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

"""Prioritize all-district evidence without treating RDH source totals as certified."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import build_pa_data_layers as layers

OUT = Path(__file__).resolve().parent / 'original_block_years'


def write(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    names = layers.county_fips_by_name()
    controls, priorities = [], []
    for year in (2016, 2018, 2020):
        source = defaultdict(int)
        with (OUT / f'{year}_county_district_party_cents.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                if row['model'] == 'rdh_block' and row['scope'] == 'congressional':
                    source[(row['contest'], row['countyfp'], row['party_bucket'])] += int(row['modeled_vote_cents'])
        for path in sorted((ROOT / 'data/benchmarks').glob(f'pa_county_{year}_*_certified.csv')):
            contest = path.stem[len(f'pa_county_{year}_'):-len('_certified')]
            with path.open(newline='') as handle:
                for row in csv.DictReader(handle):
                    county = layers.normalize_county_name(row['county'])
                    fp = names[county]
                    for field in ('dem_votes', 'rep_votes', 'other_votes'):
                        expected = int(row[field]) * 100
                        actual = source[(contest, fp, field)]
                        controls.append({'year': year, 'contest': contest, 'countyfp': fp, 'county': county,
                                         'party_bucket': field, 'rdh_source_vote_cents': actual,
                                         'certified_vote_cents': expected, 'rdh_minus_certified_vote_cents': actual - expected,
                                         'status': 'match' if actual == expected else 'source-control discrepancy; not redistributed'})
        with (OUT / f'{year}_all_district_comparisons.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        by_key = {(row['model'], row['scope'], row['contest'], row['district']): row for row in rows}
        for row in rows:
            if row['model'] != 'census_vap':
                continue
            key = row['scope'], row['contest'], row['district']
            mod = by_key[('vap_mod', *key)]
            given = by_key[('rdh_block', *key)]
            item = {key: row[key] for key in ('year', 'contest', 'scope', 'district')}
            item.update({'published_signed_margin_pct': row['published_signed_margin_pct'],
                         'original_blocks_census_vap_margin_pct': row['modeled_margin_pct'],
                         'original_blocks_vap_mod_margin_pct': mod['modeled_margin_pct'],
                         'rdh_as_given_margin_pct': given['modeled_margin_pct'],
                         'census_minus_published_margin_pp': float(row['modeled_margin_pct']) - float(row['published_signed_margin_pct']),
                         'census_minus_vap_mod_margin_pp': float(row['modeled_margin_pct']) - float(mod['modeled_margin_pct']),
                         'decision': 'review priority only; county source controls and election precinct identity must be reconciled before promotion'})
            priorities.append(item)
    priorities.sort(key=lambda row: abs(row['census_minus_published_margin_pp']), reverse=True)
    write('all_district_review_priorities.csv', priorities)
    write('rdh_source_vs_certified_county_controls.csv', controls)
    summary = {'reviewed_years': [2016, 2018, 2020], 'unique_year_contest_scope_district_rows': len(priorities),
               'county_party_control_comparisons': len(controls),
               'nonzero_source_control_differences': sum(row['rdh_minus_certified_vote_cents'] != 0 for row in controls),
               'source_control_differences_exceeding_one_vote': sum(abs(row['rdh_minus_certified_vote_cents']) > 100 for row in controls),
               'production_changes': [], 'top_12_review_priorities': priorities[:12]}
    (OUT / 'review_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({key: value for key, value in summary.items() if key != 'top_12_review_priorities'}, indent=2))


if __name__ == '__main__':
    main()

"""Read-only all-district comparison of original RDH 2016/2018/2020 blocks.

Diagnostic units are hundredths of a modeled vote, not integer ballots. No
county controls or unexplained statewide residual adjustment is performed.
"""
import csv
import hashlib
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from reconcile_pa10_original_blocks import dbf_rows

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_county_clustered_2024_district_contests as clustered
import build_pa_data_layers as layers

OUT = Path(__file__).resolve().parent / 'original_block_years'
CONTESTS = {'PRE': 'president', 'USS': 'us_senate', 'GOV': 'governor',
            'ATG': 'attorney_general', 'AUD': 'auditor', 'TRE': 'treasurer'}
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def audit_year(year, vap, assignments):
    path = ROOT.parents[1] / f'data/pa_{year}_gen_2020_blocks.zip'
    weights = defaultdict(lambda: defaultdict(lambda: defaultdict(float)))
    county_vap = defaultdict(lambda: defaultdict(float))
    precinct_cents, source = defaultdict(lambda: defaultdict(int)), defaultdict(int)
    allocated = defaultdict(int)
    universe, columns, seen = 0, {}, set()
    with zipfile.ZipFile(path) as archive:
        with archive.open(next(name for name in archive.namelist() if name.lower().endswith('.dbf'))) as stream:
            for row in dbf_rows(stream):
                block, fp, precinct = row['GEOID20'], row['COUNTYFP'].zfill(3), row['PRECINCTID']
                if block in seen or block not in vap or any(block not in values for values in assignments.values()):
                    raise ValueError(f'Duplicate or unmatched source block {block}')
                seen.add(block)
                universe += 1
                if not columns:
                    columns = {column: (CONTESTS[column[3:6]], 'dem_votes' if column[6] == 'D' else 'rep_votes' if column[6] == 'R' else 'other_votes')
                               for column in row if column.startswith(f'G{year % 100:02}') and column[3:6] in CONTESTS}
                amounts = defaultdict(int)
                for column, identity in columns.items():
                    value = float(row[column] or 0)
                    cents = round(value * 100)
                    if abs(value * 100 - cents) > 1e-6:
                        raise ValueError(f'{column}/{block}: not a hundredth-vote value; do not silently round')
                    amounts[identity] += cents
                for identity, cents in amounts.items():
                    precinct_cents[(fp, precinct)][identity] += cents
                    source[(fp, *identity)] += cents
                for scope, values in assignments.items():
                    district = values[block]
                    county_vap[(scope, fp)][district] += vap[block]
                    weights[(fp, precinct)][('census_vap', scope)][district] += vap[block]
                    weights[(fp, precinct)][('vap_mod', scope)][district] += float(row['VAP_MOD'] or 0)
                    for (contest, field), cents in amounts.items():
                        allocated[('rdh_block', scope, fp, district, contest, field)] += cents
    assert universe == 336985
    whole = {key: next(iter(districts)) for key, values in county_vap.items()
             if len(districts := clustered.classify_county_weights(values)) == 1}
    unallocated = []
    for (fp, precinct), amounts in precinct_cents.items():
        for model in ('census_vap', 'vap_mod'):
            for scope in assignments:
                district_weights = weights[(fp, precinct)][(model, scope)]
                if (scope, fp) in whole:
                    district_weights = {whole[(scope, fp)]: 1}
                for (contest, field), cents in amounts.items():
                    if not cents:
                        continue
                    if sum(district_weights.values()) <= 0:
                        unallocated.append({'year': year, 'model': model, 'scope': scope, 'countyfp': fp,
                                            'precinct': precinct, 'contest': contest, 'party_bucket': field,
                                            'unallocated_vote_cents': cents, 'reason': 'no positive source-precinct population weight'})
                        continue
                    allocation = layers.allocate_votes_by_block_counts(cents, district_weights)
                    assert sum(allocation.values()) == cents
                    for district, amount in allocation.items():
                        allocated[(model, scope, fp, district, contest, field)] += amount
    rows = [{'year': year, 'model': model, 'scope': scope, 'countyfp': fp, 'district': district,
             'contest': contest, 'party_bucket': field, 'modeled_vote_cents': cents}
            for (model, scope, fp, district, contest, field), cents in sorted(allocated.items()) if cents]
    save(f'{year}_county_district_party_cents.csv', rows)
    save(f'{year}_unallocated.csv', unallocated)
    checks = []
    for model in ('rdh_block', 'census_vap', 'vap_mod'):
        for scope in assignments:
            sums = defaultdict(int)
            for (m, s, fp, district, contest, field), cents in allocated.items():
                if (m, s) == (model, scope):
                    sums[(fp, contest, field)] += cents
            for (fp, contest, field), cents in source.items():
                checks.append({'year': year, 'model': model, 'scope': scope, 'countyfp': fp,
                               'contest': contest, 'party_bucket': field, 'source_vote_cents': cents,
                               'allocated_vote_cents': sums[(fp, contest, field)],
                               'unallocated_vote_cents': cents - sums[(fp, contest, field)]})
    save(f'{year}_county_conservation.csv', checks)
    district_values = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
    for row in rows:
        district_values[(row['model'], row['scope'], row['contest'], row['district'])][row['party_bucket']] += row['modeled_vote_cents']
    changes = []
    for (model, scope, contest, district), values in sorted(district_values.items()):
        published_path = ROOT / f'data/district_contests/{scope}_{contest}_{year}.json'
        if not published_path.exists():
            continue
        published = json.loads(published_path.read_text())['general']['results'].get(district)
        if not published:
            continue
        item = {'year': year, 'contest': contest, 'scope': scope, 'district': district, 'model': model,
                'diagnostic_only': True, 'unallocated_entries_in_slice': sum(row['model'] == model and row['scope'] == scope and row['contest'] == contest for row in unallocated)}
        for field in FIELDS:
            item[f'published_{field}'] = published[field]
            item[f'modeled_{field}_cents'] = values[field]
            item[f'modeled_minus_published_{field}_cents'] = values[field] - 100 * published[field]
        total = sum(values.values())
        item['modeled_margin_pct'] = 100 * (values['dem_votes'] - values['rep_votes']) / total if total else 0
        item['published_signed_margin_pct'] = 100 * (published['dem_votes'] - published['rep_votes']) / published['total_votes'] if published['total_votes'] else 0
        changes.append(item)
    save(f'{year}_all_district_comparisons.csv', changes)
    return {'year': year, 'archive_name': path.name, 'archive_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'block_universe': universe, 'source_precincts': len(precinct_cents), 'contest_columns': columns,
            'unallocated_entries': len(unallocated), 'county_conservation_failure_rows': sum(row['unallocated_vote_cents'] != 0 for row in checks),
            'district_comparison_rows': len(changes), 'status': 'DIAGNOSTIC_ONLY_NOT_A_PRODUCTION_CANDIDATE'}


def main():
    OUT.mkdir(exist_ok=True)
    vap = clustered.load_block_vap(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz')
    assignments = clustered.load_district_assignments()
    summaries = []
    for year in (2016, 2018, 2020):
        print(f'Auditing original {year} blocks in all three legislative scopes', flush=True)
        summaries.append(audit_year(year, vap, assignments))
        (OUT / 'summary.json').write_text(json.dumps(summaries, indent=2) + '\n')
        print(json.dumps({key: value for key, value in summaries[-1].items() if key != 'contest_columns'}), flush=True)


if __name__ == '__main__':
    main()

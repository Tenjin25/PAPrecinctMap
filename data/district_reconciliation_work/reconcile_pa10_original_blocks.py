"""Compare original RDH election-precinct blocks using VAP_MOD and Census VAP.

Reads DBF directly with the standard library; geometry is neither rewritten nor
used to invent missing assignments. All outputs are diagnostic only.
"""
import csv
import hashlib
import json
import re
import struct
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_county_clustered_2024_district_contests as clustered

OUT = Path(__file__).resolve().parent / 'pa10_original_blocks'
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


def dbf_rows(stream):
    header = stream.read(32)
    count, header_size, row_size = struct.unpack_from('<IHH', header, 4)
    descriptors = stream.read(header_size - 32)
    fields = []
    for offset in range(0, len(descriptors) - 1, 32):
        field = descriptors[offset:offset + 32]
        if len(field) < 32 or field[0] == 13:
            break
        fields.append((field[:11].split(b'\x00')[0].decode('ascii'), field[16]))
    assert 1 + sum(size for _, size in fields) == row_size
    for _ in range(count):
        raw = stream.read(row_size)
        if len(raw) != row_size:
            raise ValueError('Truncated DBF record')
        if raw[:1] == b'*':
            continue
        row, pos = {}, 1
        for name, size in fields:
            row[name] = raw[pos:pos + size].decode('utf-8').strip()
            pos += size
        yield row


def key(fp, name):
    name = re.sub(r'\s*\(Cong\.\s*\d+\)\s*$', '', name, flags=re.I)
    name = re.sub(r'\s+School District \d+\s*$', '', name, flags=re.I)
    name = name.replace('MIDDLET0N', 'MIDDLETON')
    normalized = layers.normalize_bridge_precinct_name(name)
    normalized = re.sub(r'\b(?:P|PRECINCT|D|DISTRICT|W|WARD|X)\b', ' ', normalized)
    normalized = ' '.join(re.sub(r'[^A-Z0-9]+', ' ', normalized).split())
    return fp.zfill(3), normalized


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['status'])
        writer.writeheader()
        writer.writerows(rows)


def main():
    archive_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parents[1] / 'data/pa_2018_gen_2020_blocks.zip'
    OUT.mkdir(exist_ok=True)
    vap = clustered.load_block_vap(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz')
    assignments = clustered.load_district_assignments()['congressional']
    weights = defaultdict(lambda: {'census_vap': defaultdict(float), 'vap_mod': defaultdict(float)})
    blocks, unknown, seen, original_names = [], [], set(), {}
    with zipfile.ZipFile(archive_path) as archive:
        dbf_name = next(name for name in archive.namelist() if name.lower().endswith('.dbf'))
        with archive.open(dbf_name) as stream:
            for row in dbf_rows(stream):
                block, fp = row['GEOID20'], row['COUNTYFP'].zfill(3)
                if block in seen:
                    raise ValueError(f'Duplicate source block {block}')
                seen.add(block)
                if fp not in {'041', '043', '133'}:
                    continue
                district = assignments.get(block)
                if district is None or block not in vap:
                    unknown.append({'block': block, 'reason': 'missing BEF or Census VAP'})
                    continue
                identity = key(fp, row['PRECINCTID'])
                if identity in original_names and original_names[identity] != row['PRECINCTID']:
                    raise ValueError(f'Ambiguous normalized precinct {identity}: {original_names[identity]} / {row["PRECINCTID"]}')
                original_names[identity] = row['PRECINCTID']
                mod = float(row['VAP_MOD'] or 0)
                weights[identity]['census_vap'][district] += vap[block]
                weights[identity]['vap_mod'][district] += mod
                blocks.append({'block': block, 'countyfp': fp, 'source_precinct': row['PRECINCTID'],
                               'normalized_precinct': identity[1], 'district': district,
                               'census_vap': vap[block], 'vap_mod': mod,
                               'rdh_dem_votes': row['G18USSDCAS'], 'rdh_rep_votes': row['G18USSRBAR'],
                               'rdh_lib_votes': row['G18USSLKER'], 'rdh_grn_votes': row['G18USSGGAL']})
    assert len(seen) == 336985
    assert not unknown, unknown[:5]
    records, unmatched = [], []
    totals = defaultdict(lambda: defaultdict(lambda: dict.fromkeys(FIELDS, 0)))
    with (ROOT / 'data/ElectionReturns_2018_General_PrecinctReturns.txt').open(newline='', encoding='utf-8-sig') as handle:
        for line, row in enumerate(csv.reader(handle), 1):
            if len(row) < 31 or row[8] != 'USS' or row[29].zfill(3) not in {'041', '043', '133'}:
                continue
            fp, precinct, party, votes = row[29].zfill(3), row[22], row[9], int(row[15])
            assert party in {'DEM', 'REP', 'LIB', 'GRN'}
            bucket = 'dem_votes' if party == 'DEM' else 'rep_votes' if party == 'REP' else 'other_votes'
            identity = key(fp, precinct)
            matching = 'structural_label_normalization'
            municipality_type = {'4': 'TOWNSHIP', '6': 'BOROUGH'}.get(row[21])
            if municipality_type:
                place = re.match(r'^(.*?)( \d.*)?$', identity[1])
                typed = (fp, place[1] + ' ' + municipality_type + (place[2] or ''))
                if typed in weights:
                    identity = typed
                    matching = 'official_municipality_type_and_structural_label'
            # A ward-only state label can correspond to RDH's sole division 1.
            # Never collapse a ward containing multiple named divisions.
            if identity not in weights and re.search(r'\bW\s*\d+$', precinct):
                children = [item for item in weights if item[0] == fp and item[1].startswith(identity[1] + ' ')]
                if children == [(fp, identity[1] + ' 1')]:
                    identity = children[0]
                    matching = 'unique_ward_only_division_1'
            for model in ('census_vap', 'vap_mod'):
                district_weights = weights[identity][model]
                total = sum(district_weights.values())
                if total <= 0:
                    unmatched.append({'source_line': line, 'countyfp': fp, 'precinct': precinct, 'party': party, 'votes': votes, 'model': model})
                    continue
                allocation = layers.allocate_votes_by_block_counts(votes, district_weights)
                assert sum(allocation.values()) == votes
                totals[model][fp][bucket] += allocation.get('10', 0)
                records.append({'source_line': line, 'countyfp': fp, 'precinct': precinct, 'party_bucket': bucket,
                                'official_municipality_type': row[21], 'old_congressional_label': row[18],
                                'candidate': ' '.join(row[11:15]), 'model': model, 'source_votes': votes,
                                'matched_rdh_precinct': original_names.get(identity), 'matching': matching,
                                'district_weights': json.dumps(dict(district_weights), sort_keys=True),
                                'current_cd10_fractional_votes': votes * district_weights.get('10', 0) / total,
                                'current_cd10_integer_votes': allocation.get('10', 0),
                                'all_district_allocations': json.dumps(allocation, sort_keys=True)})
    save('block_assignments.csv', blocks)
    save('precinct_allocations.csv', records)
    save('unmatched.csv', unmatched)
    pooled = defaultdict(set)
    for record in records:
        if record['model'] == 'census_vap':
            pooled[(record['countyfp'], record['matched_rdh_precinct'])].add(record['precinct'])
    for record in records:
        if len(pooled[(record['countyfp'], record['matched_rdh_precinct'])]) > 1:
            positive = [district for district, value in json.loads(record['district_weights']).items() if value > 0]
            assert len(positive) == 1, 'Do not pool explicitly localized rows across a current district boundary'
    original_path = OUT.parent / 'pa10_raw_returns/source_precinct_allocation.csv'
    with original_path.open(newline='') as handle:
        previous = {row['source_line']: row for row in csv.DictReader(handle)}
    changes = []
    for record in records:
        if record['model'] != 'census_vap':
            continue
        before = previous[str(record['source_line'])]
        delta = record['current_cd10_integer_votes'] - int(before['current_cd10_integer_votes'])
        if delta:
            changes.append({key: record[key] for key in ('source_line', 'countyfp', 'precinct', 'official_municipality_type', 'party_bucket', 'candidate', 'source_votes', 'matched_rdh_precinct', 'district_weights')})
            changes[-1].update({'via_vtd_bridge_cd10_votes': int(before['current_cd10_integer_votes']),
                               'original_blocks_cd10_votes': record['current_cd10_integer_votes'],
                               'direct_minus_bridge': delta,
                               'cause': 'municipality/precinct identity' if record['precinct'].startswith('YORK W') else 'Carter VTD aggregation loses election-precinct block distribution'})
    save('precinct_path_differences.csv', changes)
    county_checks = []
    with (ROOT / 'data/benchmarks/pa_county_2018_us_senate_certified.csv').open(newline='') as handle:
        controls = {row['county'].upper(): row for row in csv.DictReader(handle)}
    for fp, name in [('041', 'CUMBERLAND'), ('043', 'DAUPHIN'), ('133', 'YORK')]:
        for model in ('census_vap', 'vap_mod'):
            for field in FIELDS:
                selected = [row for row in records if row['countyfp'] == fp and row['model'] == model and row['party_bucket'] == field]
                allocated = sum(sum(json.loads(row['all_district_allocations']).values()) for row in selected)
                control = int(controls[name][field])
                county_checks.append({'county': name, 'model': model, 'party_bucket': field, 'allocated': allocated, 'certified': control, 'delta': allocated - control})
                if not unmatched:
                    assert allocated == control
    save('county_party_conservation.csv', county_checks)
    summary = {'archive_name': archive_path.name, 'archive_sha256': hashlib.sha256(archive_path.read_bytes()).hexdigest(),
               'block_universe': len(seen), 'benchmark_county_blocks': len(blocks),
               'unmatched_rows': len(unmatched), 'unmatched_votes': sum(row['votes'] for row in unmatched),
               'county_totals': {model: dict(counties) for model, counties in totals.items()},
               'district_totals': {model: {field: sum(county[field] for county in counties.values()) for field in FIELDS} for model, counties in totals.items()},
               'source_precinct_split_weights': [{'countyfp': fp, 'precinct': precinct,
                   **{model: dict(values) for model, values in models.items()}}
                   for (fp, precinct), models in sorted(weights.items())
                   if any(len([v for v in values.values() if v > 0]) > 1 for values in models.values())],
               'decision': 'Diagnostic only; original block-to-precinct assignments are RDH-modeled, not official ballot-fragment returns.'}
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: value for key, value in summary.items() if key != 'source_precinct_split_weights'}, indent=2))


if __name__ == '__main__':
    main()

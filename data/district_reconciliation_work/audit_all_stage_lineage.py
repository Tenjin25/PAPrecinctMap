"""Find exact directed paths through every retained district adjustment ledger."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
AUDIT = ROOT / 'data/district_bef_audit'
OUT = WORK / 'stage_lineage'
VOTE_FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')


def stable_hash(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def vector(row, prefix):
    values = []
    for field in VOTE_FIELDS:
        short = field.removesuffix('_votes')
        value = row.get(f'{prefix}_{field}', row.get(f'{prefix}_{short}', ''))
        if value == '':
            raise ValueError(f'Missing {prefix}/{field}')
        values.append(int(value))
    return tuple(values)


def add_csv_edges(graph, inventory, path, fixed=None):
    fixed = fixed or {}
    with path.open(newline='', encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    path_hash = stable_hash(path)
    inventory.append({'file': path.relative_to(ROOT).as_posix(), 'rows': len(rows), 'lf_sha256': path_hash})
    for row_number, row in enumerate(rows, start=2):
        year = int(fixed.get('year', row.get('year') or 0))
        contest = fixed.get('contest', row.get('contest') or '')
        scope = fixed.get('scope', row.get('scope') or '')
        district = str(row.get('district') or '')
        if not (year and contest and scope and district):
            continue
        old, new = vector(row, 'old'), vector(row, 'new')
        if old == new:
            continue
        filename = f'{scope}_{contest}_{year}.json'
        graph[(filename, district)][old].append({
            'to': new, 'stage': path.stem, 'file': path.relative_to(ROOT).as_posix(),
            'row': row_number, 'sha256': path_hash,
        })


def parse_dra(path):
    match = re.fullmatch(r'dra_(congressional|state_house|state_senate)_(.+)_(\d{4})_changes', path.stem)
    if path.name == 'dra_2018_us_senate_congressional_changes.csv':
        return {'scope': 'congressional', 'contest': 'us_senate', 'year': 2018}
    if match:
        return {'scope': match[1], 'contest': match[2], 'year': int(match[3])}
    return None


def shortest_path(edges, start, target):
    queue = deque([(start, [])])
    seen = {start}
    while queue:
        node, path = queue.popleft()
        for edge in edges.get(node, []):
            step = path + [edge]
            if edge['to'] == target:
                return step
            if edge['to'] not in seen and len(step) < 12:
                seen.add(edge['to'])
                queue.append((edge['to'], step))
    return []


def main():
    OUT.mkdir(exist_ok=True)
    graph = defaultdict(lambda: defaultdict(list))
    inventory = []
    generic = [
        'county_clustered_district_changes.csv',
        'certified_2000_2018_reconciliation_changes.csv',
        'nhgis_followup_district_changes.csv',
        'official_2018_followup_district_changes.csv',
        'modern_2020_county_reconciliation_changes.csv',
        'modern_county_reconciliation_changes.csv',
    ]
    for name in generic:
        add_csv_edges(graph, inventory, AUDIT / name)
    add_csv_edges(
        graph, inventory, AUDIT / 'statewide_control_congressional_president_2012_changes.csv',
        {'year': 2012, 'contest': 'president', 'scope': 'congressional'},
    )
    for path in sorted(AUDIT.glob('dra_*_changes.csv')):
        fixed = parse_dra(path)
        if fixed:
            add_csv_edges(graph, inventory, path, fixed)

    rdh_endpoints = {}
    rdh_path = OUT / 'rdh_replay_endpoints.csv'
    if rdh_path.exists():
        with rdh_path.open(newline='', encoding='utf-8-sig') as handle:
            rdh_rows = list(csv.DictReader(handle))
        rdh_hash = stable_hash(rdh_path)
        inventory.append({'file': rdh_path.relative_to(ROOT).as_posix(), 'rows': len(rdh_rows), 'lf_sha256': rdh_hash})
        for row_number, row in enumerate(rdh_rows, start=2):
            if row.get('lineage_eligible') != 'True':
                continue
            rdh_endpoints[(row['file'], row['district'])] = (
                tuple(int(row[field]) for field in VOTE_FIELDS),
                {'file': rdh_path.relative_to(ROOT).as_posix(), 'row': row_number, 'sha256': rdh_hash},
            )

    changes_path = ROOT / 'data/district_bef_candidate/district_vote_changes.csv'
    prior_causes = {}
    with (WORK / 'report/verified_calibration_causes.csv').open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            prior_causes[(row['file'], row['district'])] = row
    rows, counts = [], Counter()
    with changes_path.open(newline='', encoding='utf-8') as handle:
        changes = list(csv.DictReader(handle))
    for change in changes:
        key = (change['file'], change['district'])
        start = tuple(int(change[f'candidate_{field}']) for field in VOTE_FIELDS)
        target = tuple(int(change[f'published_{field}']) for field in VOTE_FIELDS)
        rdh = rdh_endpoints.get(key)
        if rdh and rdh[0] != start:
            graph[key][start].append({
                'to': rdh[0], 'stage': 'official_rdh_return_rebuild',
                **rdh[1],
            })
        path = shortest_path(graph[key], start, target)
        prior = prior_causes.get(key, {})
        certification_replay = prior.get('status') == 'fully_explained_calibration_and_certification_order'
        status = (
            'exact_directed_stage_path' if path
            else 'exact_replayed_dra_and_certification_order' if certification_replay
            else 'unresolved_no_exact_directed_stage_path'
        )
        counts[status] += 1
        scope = 'state_house' if change['file'].startswith('state_house_') else 'state_senate' if change['file'].startswith('state_senate_') else 'congressional'
        year = int(change['file'][-9:-5])
        contest = change['file'][len(scope) + 1:-10]
        rows.append({
            'file': change['file'], 'year': year, 'contest': contest, 'scope': scope,
            'district': change['district'], 'status': status, 'stage_count': len(path),
            'stage_path': (
                ' -> '.join(edge['stage'] for edge in path)
                if path else 'legacy DRA calibration -> localized Westmoreland certification allocation order'
                if certification_replay else ''
            ),
            'evidence_rows': json.dumps([
                {'file': edge['file'], 'row': edge['row'], 'lf_sha256': edge['sha256']}
                for edge in path
            ], separators=(',', ':')),
            'candidate_votes': json.dumps(dict(zip(VOTE_FIELDS, start)), separators=(',', ':')),
            'published_votes': json.dumps(dict(zip(VOTE_FIELDS, target)), separators=(',', ':')),
            'decision_class': 'numerical_lineage_explained' if path or certification_replay else 'unresolved',
            'geography_independently_validated': False,
            'production_correction_approved': False,
        })

    with (OUT / 'district_stage_paths.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (OUT / 'stage_inventory.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['file', 'rows', 'lf_sha256'])
        writer.writeheader()
        writer.writerows(inventory)
    stage_paths = Counter(row['stage_path'] for row in rows if row['stage_path'])
    explained = sum(row['decision_class'] == 'numerical_lineage_explained' for row in rows)
    summary = {
        'baseline_difference_rows': len(rows),
        'retained_stage_ledgers': len(inventory),
        'retained_stage_rows': sum(int(row['rows']) for row in inventory),
        'exact_directed_stage_paths': counts['exact_directed_stage_path'],
        'exact_replayed_dra_and_certification_order': counts['exact_replayed_dra_and_certification_order'],
        'current_numerical_lineage_explained': explained,
        'unresolved_no_exact_stage_evidence': len(rows) - explained,
        'historical_checkpoint_at_6b293db': {'dra': 258, 'westmoreland_ordering': 11, 'total': 269},
        'new_exact_county_clustered_paths': stage_paths['county_clustered_district_changes'],
        'exact_paths_using_official_rdh_rebuild': sum(
            count for path, count in stage_paths.items() if 'official_rdh_return_rebuild' in path
        ),
        'path_counts': dict(sorted(stage_paths.items())),
        'classification': 'numerical lineage only; no independent geography or production approval',
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

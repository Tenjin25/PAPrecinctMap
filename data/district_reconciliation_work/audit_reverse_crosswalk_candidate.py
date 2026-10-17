"""Replay only rows that actually invoke the current-precinct reverse fallback.

The production allocator historically discarded directed source-VTD -> current-
precinct shares when reversing ``pa_vtd20_to_current_precinct.csv``.  This
diagnostic leaves production untouched, compares that full-VTD-union behavior
with a share-preserving candidate, and emits source-row and paired-transfer
evidence.  It never applies the resulting delta to calibrated publication.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_pa_precinct_returns as precinct
import build_county_clustered_2024_district_contests as clustered

OUT = Path(__file__).resolve().parent / 'reverse_crosswalk_candidate'
PARTY_FIELDS = ('dem_votes', 'rep_votes', 'other_votes')
SCOPES = ('congressional', 'state_house', 'state_senate')


def stable_hash(path: Path) -> str:
    content = path.read_bytes()
    if path.suffix.lower() in {'.csv', '.json', '.txt', '.py', '.md'}:
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def save_csv(name: str, rows: list[dict], fields: list[str] | None = None) -> None:
    path = OUT / name
    fields = fields or (list(rows[0]) if rows else ['status'])
    with path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def district_weights(targets, scope, maps):
    weights = defaultdict(float)
    for county, vtd, share, *_method in targets:
        for district, vap in (maps[scope].get((county, vtd)) or {}).items():
            weights[str(district)] += float(share) * float(vap)
    return dict(sorted(weights.items(), key=lambda item: int(item[0])))


def party_field(row):
    party = str(row.get('party') or '').strip().upper()
    if party in layers.PARTY_DEM or party == 'YES':
        return 'dem_votes'
    if party in layers.PARTY_REP or party == 'NO':
        return 'rep_votes'
    return 'other_votes'


def load_layer(directory: Path, filename: str):
    path = directory / filename
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    return payload.get('general', {}).get('results', {})


def read_normalized_rows(path: Path):
    """Read a normalized OpenElections derivative with the standard CSV parser."""
    with path.open('r', encoding='utf-8-sig', errors='ignore', newline='') as handle:
        rows = list(csv.DictReader(handle))
    rows = layers.infer_missing_parties(rows)
    return [row for row in rows if not layers.is_summary_result_row(row)]


def main():
    OUT.mkdir(exist_ok=True)
    selected_years = {int(value) for value in sys.argv[1:]} if len(sys.argv) > 1 else set()
    candidate_temp = tempfile.TemporaryDirectory(
        prefix='_generated_candidate_',
        dir=OUT,
    )
    candidate_dir = Path(candidate_temp.name)
    layers.build_district_manifests(
        candidate_dir,
        years=selected_years or None,
        apply_reviewed_corrections=False,
    )
    maps, county_districts, block_vap_count, carter_block_count = clustered.build_vap_maps(
        ROOT / 'data/crosswalks/pa_block20_vap.csv.gz',
        ROOT / 'data/BlockAssign_ST42_PA.zip',
    )
    layers._load_current_precinct_vtd_targets()
    share_sensitive_keys = set()
    for current_key, targets in (layers.CURRENT_PRECINCT_TO_WEIGHTED_VTDS or {}).items():
        if len(targets) <= 1:
            continue
        old_targets = [(c, v, 1.0, 'legacy_full_vtd_union') for c, v in targets]
        corrected_targets = [
            (c, v, share, f'current_precinct_forward_share:{method}')
            for (c, v), (share, method) in targets.items()
        ]
        if any(
            district_weights(old_targets, scope, maps) != district_weights(corrected_targets, scope, maps)
            for scope in SCOPES
        ):
            share_sensitive_keys.add(current_key)
    county_fips = layers.county_fips_by_name()
    actual = Counter()
    preempted = Counter()
    affected_rows = []
    delta = Counter()
    county_totals = defaultdict(lambda: Counter(old=0, corrected=0))
    fingerprints = {}
    scanned_files = []

    for year, filename in sorted(precinct.TARGETS.items()):
        if selected_years and year not in selected_years:
            continue
        source = ROOT / 'data/Openelections' / str(year) / filename
        if not source.exists():
            continue
        print(f'reverse-crosswalk candidate: {year} {filename}', flush=True)
        fingerprints[source.relative_to(ROOT).as_posix()] = stable_hash(source)
        scanned_files.append(source.relative_to(ROOT).as_posix())
        rows = read_normalized_rows(source)
        rows = layers.apply_official_county_party_controls(rows, year)
        maintained_cache = {}
        fallback_cache = {}
        for source_index, row in enumerate(rows, start=1):
            contest = layers.office_mapping_for_contest(row.get('office') or '')
            votes = layers.safe_int(row.get('votes'))
            if not layers.is_statewide_contest_type(contest) or votes <= 0:
                continue
            county = layers.normalize_county_name(row.get('county') or '')
            countyfp = county_fips.get(county, '')
            canonical = re.search(r'\b([0-9][0-9A-Z]{5,})$', str(row.get('precinct') or '').strip().upper())
            if not canonical or (countyfp, canonical.group(1)) not in share_sensitive_keys:
                continue
            geography_key = (year, countyfp, row.get('precinct') or '', str(row.get('source_vtd') or ''))
            if geography_key not in maintained_cache:
                maintained_cache[geography_key] = layers.maintained_targets_for_row(row, year, countyfp) if countyfp else []
            maintained = [
                target for target in maintained_cache[geography_key]
                if any(maps[scope].get((target[0], target[1])) for scope in SCOPES)
            ]
            if maintained:
                preempted[(year, contest, county)] += 1
                continue
            fallback_key = (county, row.get('precinct') or '')
            if fallback_key not in fallback_cache:
                old_pairs = layers.match_row_to_current_vtds(row)
                corrected = layers.match_row_to_current_vtd_targets(row)
                fallback_cache[fallback_key] = (
                    [(c, v, 1.0, 'legacy_full_vtd_union') for c, v in old_pairs],
                    corrected,
                )
            old_targets, corrected_targets = fallback_cache[fallback_key]
            if not corrected_targets or not any(
                method.startswith('current_precinct_forward_share:')
                for _c, _v, _share, method in corrected_targets
            ):
                continue
            field = party_field(row)
            actual[(year, contest, county, field)] += 1
            for scope in SCOPES:
                old_weights = district_weights(old_targets, scope, maps)
                corrected_weights = district_weights(corrected_targets, scope, maps)
                old_alloc = layers.allocate_votes_by_block_counts(votes, old_weights)
                corrected_alloc = layers.allocate_votes_by_block_counts(votes, corrected_weights)
                if sum(old_alloc.values()) != votes or sum(corrected_alloc.values()) != votes:
                    raise RuntimeError(
                        f'Unallocated fallback row: {year}/{contest}/{county}/'
                        f'{row.get("precinct")}/{scope}'
                    )
                conservation_key = (year, contest, scope, county, field)
                county_totals[conservation_key]['old'] += sum(old_alloc.values())
                county_totals[conservation_key]['corrected'] += sum(corrected_alloc.values())
                if old_alloc == corrected_alloc:
                    continue
                for district in set(old_alloc) | set(corrected_alloc):
                    delta[(year, contest, scope, county, str(district), field)] += (
                        corrected_alloc.get(district, 0) - old_alloc.get(district, 0)
                    )
                affected_rows.append({
                    'year': year,
                    'contest': contest,
                    'scope': scope,
                    'county': county,
                    'countyfp': countyfp,
                    'source_file': source.relative_to(ROOT).as_posix(),
                    'source_row_index': source_index,
                    'precinct': row.get('precinct') or '',
                    'candidate': row.get('candidate') or '',
                    'party': row.get('party') or '',
                    'party_bucket': field,
                    'source_votes': votes,
                    'old_targets': json.dumps(old_targets, separators=(',', ':')),
                    'corrected_targets': json.dumps(corrected_targets, separators=(',', ':')),
                    'old_district_vap': json.dumps(old_weights, sort_keys=True, separators=(',', ':')),
                    'corrected_district_vap': json.dumps(corrected_weights, sort_keys=True, separators=(',', ':')),
                    'old_allocations': json.dumps(old_alloc, sort_keys=True, separators=(',', ':')),
                    'corrected_allocations': json.dumps(corrected_alloc, sort_keys=True, separators=(',', ':')),
                    'cause': 'reverse_fallback_discarded_forward_split_shares',
                    'status': 'isolated_candidate_not_production_approved',
                })

    conservation = []
    for key, values in sorted(county_totals.items()):
        year, contest, scope, county, field = key
        conservation.append({
            'year': year, 'contest': contest, 'scope': scope, 'county': county,
            'party_bucket': field, 'old_votes': values['old'],
            'corrected_votes': values['corrected'],
            'delta': values['corrected'] - values['old'],
            'conserved': values['old'] == values['corrected'],
        })
    if any(not row['conserved'] for row in conservation):
        raise RuntimeError('County-party conservation failed')

    district_rows = []
    grouped_delta = Counter()
    for (year, contest, scope, county, district, field), amount in delta.items():
        if amount:
            grouped_delta[(year, contest, scope, district, field)] += amount
    files = defaultdict(set)
    for year, contest, scope, district, _field in grouped_delta:
        files[(year, contest, scope)].add(district)
    for (year, contest, scope), districts in sorted(files.items()):
        filename = f'{scope}_{contest}_{year}.json'
        input_path = ROOT / 'data/district_contests' / filename
        if input_path.exists():
            fingerprints[input_path.relative_to(ROOT).as_posix()] = stable_hash(input_path)
        generic = load_layer(candidate_dir, filename)
        published = load_layer(ROOT / 'data/district_contests', filename)
        calibrated = 'dra_share_calibration' in str(
            json.loads((ROOT / 'data/district_contests' / filename).read_text(encoding='utf-8')).get('meta', {}).get('source', '')
        ) if (ROOT / 'data/district_contests' / filename).exists() else False
        reviewed = bool(
            json.loads((ROOT / 'data/district_contests' / filename).read_text(encoding='utf-8')).get('meta', {}).get('reviewed_precinct_corrections')
        ) if (ROOT / 'data/district_contests' / filename).exists() else False
        reviewed_districts = {'131', '134'} if reviewed and year == 2016 and scope == 'state_house' else set()
        for district in sorted(districts, key=int):
            review_overlap = district in reviewed_districts
            row = {
                'file': filename, 'year': year, 'contest': contest, 'scope': scope,
                'district': district, 'calibrated_publication': calibrated,
                'reviewed_correction_present': reviewed,
                'reviewed_correction_district_overlap': review_overlap,
                'production_disposition': (
                    'blocked_mixed_with_reviewed_emmaus_requires_full_rebuild' if review_overlap
                    else 'blocked_no_precalibration_delta_on_calibrated_publication' if calibrated
                    else 'diagnostic_pending_independent_geography_validation'
                ),
            }
            for field in PARTY_FIELDS:
                change = grouped_delta.get((year, contest, scope, district, field), 0)
                before = int((generic.get(district) or {}).get(field, 0)) if generic else ''
                row[f'{field}_delta'] = change
                row[f'generic_before_{field}'] = before
                row[f'candidate_after_{field}'] = before + change if before != '' else ''
                row[f'published_{field}'] = int((published.get(district) or {}).get(field, 0)) if published else ''
            row['total_votes_delta'] = sum(row[f'{field}_delta'] for field in PARTY_FIELDS)
            district_rows.append(row)

    statewide_delta = Counter()
    for (year, contest, scope, _county, _district, field), amount in delta.items():
        statewide_delta[(year, contest, scope, field)] += amount
    if any(statewide_delta.values()):
        raise RuntimeError(f'Statewide-party transfer imbalance: {dict(statewide_delta)}')

    paired = []
    for (year, contest, scope, county, district, field), amount in sorted(delta.items()):
        if amount:
            paired.append({
                'year': year, 'contest': contest, 'scope': scope, 'county': county,
                'district': district, 'party_bucket': field, 'vote_transfer': amount,
                'cause': 'reverse_fallback_discarded_forward_split_shares',
            })

    decisions = []
    decision_groups = defaultdict(lambda: {'source_rows': set(), 'votes': 0, 'districts': set()})
    for row in affected_rows:
        key = (row['year'], row['contest'], row['scope'], row['county'])
        decision_groups[key]['source_rows'].add((row['source_file'], row['source_row_index']))
        decision_groups[key]['votes'] += int(row['source_votes'])
        decision_groups[key]['districts'].update(json.loads(row['old_allocations']))
        decision_groups[key]['districts'].update(json.loads(row['corrected_allocations']))
    for key, values in sorted(decision_groups.items()):
        year, contest, scope, county = key
        decisions.append({
            'year': year, 'contest': contest, 'scope': scope, 'county': county,
            'cause': 'reverse_fallback_discarded_forward_split_shares',
            'decision_class': 'numerical_lineage_explained_candidate_only',
            'affected_source_rows': len(values['source_rows']),
            'affected_source_votes_scope_counted': values['votes'],
            'affected_district_rows': len(values['districts']),
            'source_complete': True,
            'geography_independently_validated': False,
            'production_correction_approved': False,
            'disposition': 'retain_publication_pending_independent_geography_review',
        })

    for path in (
        ROOT / 'data/crosswalks/pa_vtd20_to_current_precinct.csv',
        ROOT / 'data/crosswalks/pa_block20_vap.csv.gz',
        ROOT / 'data/BlockAssign_ST42_PA.zip',
        ROOT / 'data/42_PA_CD118.txt',
        ROOT / 'data/42_PA_SLDL22.txt',
        ROOT / 'data/42_PA_SLDU22.txt',
    ):
        fingerprints[path.relative_to(ROOT).as_posix()] = stable_hash(path)

    save_csv('affected_source_rows.csv', affected_rows)
    save_csv('county_party_conservation.csv', conservation)
    save_csv('county_district_party_transfers.csv', paired)
    save_csv('district_change_candidate.csv', district_rows)
    save_csv('decision_ledger.csv', decisions)
    actual_summary = [
        {'year': key[0], 'contest': key[1], 'county': key[2], 'party_bucket': key[3], 'actual_fallback_rows': count}
        for key, count in sorted(actual.items())
    ]
    save_csv('actual_fallback_summary.csv', actual_summary)
    summary = {
        'status': 'DIAGNOSTIC_ONLY',
        'normalized_source_files_scanned': scanned_files,
        'selected_years': sorted(selected_years) if selected_years else 'all retained years',
        'actual_forward_share_fallback_rows': sum(actual.values()),
        'affected_source_row_scope_pairs': len(affected_rows),
        'affected_unique_source_rows': len({(r['source_file'], r['source_row_index']) for r in affected_rows}),
        'affected_district_rows': len(district_rows),
        'decision_groups': len(decisions),
        'county_party_conservation_failures': sum(not row['conserved'] for row in conservation),
        'whole_county_threshold': clustered.WHOLE_COUNTY_THRESHOLD,
        'whole_county_rule_uses': 'Census VAP, never block counts',
        'allocation_rounding': 'deterministic largest remainder',
        'candidate_names': 'source labels retained; no name mutation in this replay',
        'emmaus_disposition': 'existing reviewed correction supersedes candidate fallback; never layer both',
        'calibrated_publication_disposition': 'no pre-calibration candidate delta applied to publication',
        'production_changes': [],
        'block_vap_records': block_vap_count,
        'carter_block_records': carter_block_count,
        'preempted_by_maintained_mapping_rows': sum(preempted.values()),
        'share_sensitive_current_precinct_keys': len(share_sensitive_keys),
    }
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    (OUT / 'input_fingerprints.json').write_text(json.dumps(fingerprints, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    candidate_temp.cleanup()
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

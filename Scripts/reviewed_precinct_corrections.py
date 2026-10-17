"""Fail-closed, source-bound corrections for individually reviewed precincts.

This does not invert crosswalk shares or distribute residuals. A review binds
the entire baseline layer, every source input, county evidence, and explicit
before/after allocations of original precinct votes. Unexpected inputs require
a new review, not a best-effort application.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

FIELDS = ('dem_votes', 'rep_votes', 'other_votes', 'total_votes')


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def vote_hash(payload):
    return canonical_hash({d: {f: r[f] for f in FIELDS} for d, r in payload['general']['results'].items()})


def source_hash(path):
    content = path.read_bytes()
    if path.suffix.lower() in ('.csv', '.txt'):
        content = content.replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def verify_counties(payload, audit):
    """Independently prove source -> county -> district party conservation."""
    districts = {}
    if not audit.get('counties'):
        raise ValueError('Reviewed correction requires all county evidence')
    for county, evidence in audit['counties'].items():
        total = dict.fromkeys(FIELDS, 0)
        for district, row in evidence['district_allocations'].items():
            if any(type(row[f]) is not int or row[f] < 0 for f in FIELDS):
                raise ValueError(f'Invalid county vote quantity: {county}/{district}')
            if sum(row[f] for f in FIELDS[:3]) != row['total_votes']:
                raise ValueError(f'County party components disagree: {county}/{district}')
            target = districts.setdefault(district, dict.fromkeys(FIELDS, 0))
            for field in FIELDS:
                total[field] += row[field]
                target[field] += row[field]
        if total != evidence['source'] or total != evidence['allocated']:
            raise ValueError(f'County votes not conserved: {county}')
    actual = {d: {f: r[f] for f in FIELDS} for d, r in payload['general']['results'].items()}
    if districts != actual:
        raise ValueError('County evidence does not reproduce the entire district layer')


def finalize(row):
    row['total_votes'] = sum(row[f] for f in FIELDS[:3])
    margin = row['dem_votes'] - row['rep_votes']
    row['winner'] = ('D' if margin > 0 else 'R' if margin < 0 else 'T') if row['total_votes'] else ''
    row['margin'] = float(abs(margin))
    row['margin_pct'] = 100 * abs(margin) / row['total_votes'] if row['total_votes'] else 0


def apply_reviewed_correction(payload, review, root):
    """Mutate only after every check passes. Return whether a change was applied."""
    entries = [entry for entry in review['entries'] if all(payload.get(k) == entry[k] for k in ('year', 'scope', 'contest_type'))]
    if not entries:
        return False
    if review.get('version') != 1 or len(entries) != 1:
        raise ValueError('Unsupported or ambiguous reviewed correction')
    root = Path(root).resolve()
    for name, expected in review['input_hashes'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or source_hash(path) != expected:
            raise ValueError(f'Reviewed correction source changed: {name}')
    entry = entries[0]
    existing = payload.get('meta', {}).get('reviewed_precinct_corrections', [])
    if vote_hash(payload) == entry['corrected_vote_hash']:
        if not any(r.get('id') == review['id'] and r.get('review_hash') == canonical_hash(review) for r in existing):
            raise ValueError('Corrected votes have no matching review receipt')
        verify_counties(payload, payload['meta']['county_conservation_audit'])
        return False
    if existing or vote_hash(payload) != entry['baseline_vote_hash']:
        raise ValueError('Reviewed correction baseline changed; new review required')
    allocation = payload['meta']['allocation_audit']
    if any(int(allocation.get(k, 0)) for k in ('unmatched_rows', 'unmatched_votes', 'unallocated_rows', 'unallocated_votes')):
        raise ValueError('Reviewed correction cannot hide unmatched or unallocated rows')
    if not allocation.get('conserved_for_matched_rows'):
        raise ValueError('Reviewed correction requires a conserved source allocation')
    county_audit = copy.deepcopy(entry['baseline_county_audit'])
    verify_counties(payload, county_audit)
    if payload['meta'].get('county_conservation_audit'):
        verify_counties(payload, payload['meta']['county_conservation_audit'])
        # Equal district totals alone cannot prove the same county contributions.
        actual_counties = payload['meta']['county_conservation_audit']['counties']
        if any(actual_counties.get(c, {}).get('district_allocations') != a['district_allocations']
               for c, a in county_audit['counties'].items()) or set(actual_counties) != set(county_audit['counties']):
            raise ValueError('Reviewed county attribution changed; new review required')
    result = copy.deepcopy(payload)
    county = county_audit['counties']['LEHIGH']['district_allocations']
    changed, seen = set(), set()
    for transfer in entry['transfers']:
        identity = (transfer['precinct'], transfer['party_bucket'])
        if identity in seen or transfer['contest'] != entry['contest_type']:
            raise ValueError('Duplicate or wrong-contest reviewed precinct row')
        seen.add(identity)
        field, votes = transfer['party_bucket'], transfer['official_votes']
        if field not in FIELDS[:3] or type(votes) is not int or votes < 0:
            raise ValueError('Invalid reviewed source vote quantity')
        for side in ('before', 'after'):
            if any(type(n) is not int or n < 0 for n in transfer[side].values()) or sum(transfer[side].values()) != votes:
                raise ValueError('Reviewed precinct votes not conserved')
        if transfer['after'] != {'134': votes}:
            raise ValueError('Emmaus review must preserve whole precinct in House 134')
        for district in set(transfer['before']) | set(transfer['after']):
            delta = transfer['after'].get(district, 0) - transfer['before'].get(district, 0)
            county[district][field] += delta
            county[district]['total_votes'] += delta
            result['general']['results'][district][field] += delta
            if delta:
                changed.add(district)
    for district in changed:
        finalize(result['general']['results'][district])
    result['meta']['county_conservation_audit'] = county_audit
    result['meta']['reviewed_precinct_corrections'] = [{
        'id': review['id'], 'review_hash': canonical_hash(review),
        'cause': 'reverse_many_to_many_crosswalk_full_vtd_union',
        'county': 'LEHIGH', 'precincts': sorted({r['precinct'] for r in entry['transfers']}),
        'geography_basis': review['geography_basis'], 'source': review['official_plan_source'],
    }]
    verify_counties(result, county_audit)
    if vote_hash(result) != entry['corrected_vote_hash']:
        raise ValueError('Reviewed correction output differs from the approved district rows')
    # All candidate labels and all unrelated district fields survive verbatim.
    payload.clear()
    payload.update(result)
    return True


def apply_local_reviews(payload, data_dir):
    path = Path(data_dir) / 'benchmarks/reviewed_emmaus_2016.json'
    if path.exists() and payload.get('year') == 2016 and payload.get('scope') == 'state_house':
        apply_reviewed_correction(payload, json.loads(path.read_text(encoding='utf-8')), Path(data_dir).parent)

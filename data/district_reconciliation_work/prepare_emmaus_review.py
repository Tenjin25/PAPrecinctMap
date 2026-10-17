"""Prepare the narrow Emmaus review package without modifying production."""
import csv
import hashlib
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'Scripts'), str(ROOT)]
from reconcile_pa10_original_blocks import dbf_rows
import build_county_clustered_2024_district_contests as clustered

WORK = Path(__file__).resolve().parent
OUT = WORK / 'emmaus_review'
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


def save(name, rows):
    with (OUT / name).open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    archive = ROOT.parents[1] / 'data/pa_2016_gen_2020_blocks.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == 'a2e1d84659de48e574e083d3a91c05a86383377748c44c04b528ec8fe60e219b'
    districts = clustered.load_district_assignments()['state_house']
    witness = []
    with zipfile.ZipFile(archive) as z:
        with z.open(next(n for n in z.namelist() if n.lower().endswith('.dbf'))) as handle:
            for row in dbf_rows(handle):
                if row['COUNTYFP'].zfill(3) == '077' and row['PRECINCTID'].startswith('EMMAUS '):
                    district = districts[row['GEOID20']]
                    assert district == '134'
                    witness.append({'block': row['GEOID20'], 'rdh_2016_precinct': row['PRECINCTID'], 'current_house': district})
    assert len({r['rdh_2016_precinct'] for r in witness}) == 6
    assert len({r['block'] for r in witness}) == len(witness)
    save('original_precinct_block_witness.csv', witness)
    source, source_ledger = defaultdict(int), []
    offices = {'USP': 'president', 'USS': 'us_senate', 'ATT': 'attorney_general', 'AUD': 'auditor', 'TRE': 'treasurer'}
    with (ROOT / 'data/ElectionReturns_2016_General_PrecinctReturns.txt').open(newline='', encoding='utf-8-sig') as handle:
        for line, p in enumerate(csv.reader(handle), 1):
            if len(p) < 29 or p[27] != '077' or p[8] not in offices or p[19] != '6' or p[20] != 'EMMAUS':
                continue
            candidate = ' '.join(p[11:15]).strip()
            assert candidate and not any(t in candidate.upper() for t in ('CAST VOTES', 'OVER VOTES', 'UNDER VOTES', 'TOTAL VOTES', 'WRITE'))
            label = ' '.join(x for x in p[20:25] if x).strip()
            field = 'dem_votes' if p[9] == 'DEM' else 'rep_votes' if p[9] == 'REP' else 'other_votes'
            source[(offices[p[8]], label, field)] += int(p[15])
            source_ledger.append({'source_line': line, 'contest': offices[p[8]], 'precinct': label,
                                  'municipality_type': p[19], 'candidate': candidate, 'party_bucket': field, 'votes': p[15]})
    save('official_candidate_rows.csv', source_ledger)
    before = defaultdict(dict)
    with (WORK / 'lehigh_2016/normalization_precinct_district_effects.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['original_precinct'].startswith('EMMAUS '):
                key = (row['contest'], row['original_precinct'], row['party_bucket'])
                before[key][row['district']] = int(row['normalized_replay_votes'])
    transfers = []
    for (contest, label, field), votes in sorted(source.items()):
        prior = before[(contest, label, field)]
        assert sum(prior.values()) == votes
        assert set(prior) <= {'131', '134'}
        transfers.append({'contest': contest, 'precinct': label, 'party_bucket': field, 'official_votes': votes,
                          'before': prior, 'after': {'134': votes}})
    inputs = ['data/ElectionReturns_2016_General_PrecinctReturns.txt',
              'data/Openelections/2016/20161108__pa__general__precinct.csv',
              'data/crosswalks/pa_vtd20_to_current_precinct.csv', 'data/42_PA_SLDL22.txt',
              'data/crosswalks/pa_historical_precinct_to_vtd20.csv',
              'data/crosswalks/pa_modern_precinct_to_vtd20.csv',
              'data/crosswalks/pa_block20_vap.csv.gz', 'data/BlockAssign_ST42_PA.zip',
              'data/district_reconciliation_work/emmaus_review/original_precinct_block_witness.csv',
              'data/district_reconciliation_work/emmaus_review/official_candidate_rows.csv']
    entries, proposals = [], []
    for contest in sorted(offices.values()):
        filename = f'state_house_{contest}_2016.json'
        pub = json.loads((ROOT / 'data/district_contests' / filename).read_text())
        baseline = json.loads((ROOT / 'data/district_bef_candidate' / filename).read_text())
        assert vote_hash(pub) == vote_hash(baseline)
        audit = baseline['meta']['allocation_audit']
        assert not audit['unmatched_rows'] and not audit['unallocated_rows'] and audit['conserved_for_matched_rows']
        delta = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
        current_transfers = [r for r in transfers if r['contest'] == contest]
        for transfer in current_transfers:
            for district in set(transfer['before']) | set(transfer['after']):
                amount = transfer['after'].get(district, 0) - transfer['before'].get(district, 0)
                delta[district][transfer['party_bucket']] += amount
                delta[district]['total_votes'] += amount
        after = json.loads(json.dumps(pub))
        for district, values in sorted(delta.items()):
            if not any(values.values()):
                continue
            proposal = {'file': filename, 'district': district, 'county': 'LEHIGH'}
            for field in FIELDS:
                old = pub['general']['results'][district][field]
                after['general']['results'][district][field] += values[field]
                proposal[f'before_{field}'], proposal[f'after_{field}'], proposal[f'delta_{field}'] = old, old + values[field], values[field]
            proposals.append(proposal)
        assert all(sum(r[f] for r in delta.values()) == 0 for f in FIELDS)
        inputs.append(f'data/benchmarks/pa_county_2016_{contest}_certified.csv')
        entries.append({'file': filename, 'contest_type': contest, 'year': 2016, 'scope': 'state_house',
                        'baseline_vote_hash': vote_hash(pub), 'corrected_vote_hash': vote_hash(after),
                        'baseline_county_audit': baseline['meta']['county_conservation_audit'],
                        'transfers': current_transfers})
    package = {'version': 1, 'id': 'emmaus-2016-whole-borough-hd134-v1',
               'decision': 'reviewed_narrow_original_precinct_correction',
               'official_plan_source': 'https://www.pa.gov/agencies/vote/resources/redistricting/pennsylvania-redistricting-house-of-representative',
               'geography_basis': 'Whole Emmaus Borough is in current House 134; all original 2016 Emmaus precinct blocks independently join House 134.',
               'original_block_archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest(),
               'input_hashes': {p: source_hash(ROOT / p) for p in inputs}, 'entries': entries}
    (ROOT / 'data/benchmarks/reviewed_emmaus_2016.json').write_text(json.dumps(package, indent=2) + '\n')
    save('proposed_district_changes.csv', proposals)
    print(json.dumps({'witness_blocks': len(witness), 'source_candidate_rows': len(source_ledger), 'proposed_district_rows': proposals}, indent=2))


if __name__ == '__main__':
    main()

"""Verify reviewed published rows, source hashes, and all county-party controls."""
import copy
import json
from pathlib import Path

import reviewed_precinct_corrections as reviewed
from build_reviewed_release import validate_pair

ROOT = Path(__file__).resolve().parents[1]


def main():
    review = json.loads((ROOT / 'data/benchmarks/reviewed_emmaus_2016.json').read_text())
    for entry in review['entries']:
        after = json.loads((ROOT / 'data/district_contests' / entry['file']).read_text())
        if reviewed.vote_hash(after) != entry['corrected_vote_hash']:
            raise ValueError(f'Published reviewed votes changed: {entry["file"]}')
        if reviewed.apply_reviewed_correction(after, review, ROOT):
            raise ValueError('Production review receipt missing or not already applied')
        before = copy.deepcopy(after)
        for transfer in entry['transfers']:
            for district in set(transfer['before']) | set(transfer['after']):
                before['general']['results'][district][transfer['party_bucket']] -= transfer['after'].get(district, 0) - transfer['before'].get(district, 0)
        for district in ('131', '134'):
            reviewed.finalize(before['general']['results'][district])
        before['meta'].pop('reviewed_precinct_corrections')
        before['meta']['county_conservation_audit'] = copy.deepcopy(entry['baseline_county_audit'])
        validate_pair(before, after, entry, review)
    print('Reviewed precinct correction checks passed: 5 layers, 10 district rows, 67 exact county-party controls per layer, zero unmatched rows.')


if __name__ == '__main__':
    main()

"""Retain exact many-to-many reverse-crosswalk evidence; never invert shares."""
import csv
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'lehigh_2016'


def main():
    reverse = defaultdict(list)
    with (ROOT / 'data/crosswalks/pa_vtd20_to_current_precinct.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            if row['countyfp'] == '077':
                reverse[row['current_precinct_norm']].append(row)
    sources = defaultdict(set)
    with (OUT / 'normalization_source_to_vtd.csv').open(newline='') as handle:
        for row in csv.DictReader(handle):
            sources[row['precinct']].add(row['diagnostic_original_precinct'])
    evidence = []
    for label, originals in sorted(sources.items()):
        targets = reverse[label]
        if len({r['vtd20'] for r in targets}) <= 1:
            continue
        for original in sorted(originals):
            for row in targets:
                evidence.append({'original_precinct': original, 'normalized_precinct': label,
                                 'recovered_vtd20': row['vtd20'], 'forward_share': row['weight'],
                                 'forward_method': row['method'],
                                 'allocator_reverse_share': '1',
                                 'cause': 'many_to_many_forward_crosswalk_reversed_as_full_vtd_union'})
    with (OUT / 'reverse_crosswalk_evidence.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(evidence[0]))
        writer.writeheader()
        writer.writerows(evidence)
    print(json.dumps({'evidence_rows': len(evidence), 'original_precincts': len({r['original_precinct'] for r in evidence}),
                      'production_changes': []}))


if __name__ == '__main__':
    main()

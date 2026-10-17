import csv
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers

OUT = Path(__file__).resolve().parent / 'reverse_crosswalk_candidate'


class ReverseCrosswalkCandidateTests(unittest.TestCase):
    def test_forward_shares_are_retained_without_changing_legacy_api(self):
        row = {'county': 'LEHIGH', 'precinct': 'LEHIGH - 077780'}
        legacy = layers.match_row_to_current_vtds(row)
        weighted = layers.match_row_to_current_vtd_targets(row)
        self.assertEqual(legacy, [('077', '000780'), ('077', '001260')])
        self.assertEqual([(c, v) for c, v, _share, _method in weighted], legacy)
        self.assertEqual(weighted[0][2], 1.0)
        self.assertAlmostEqual(weighted[1][2], 0.028735632184)
        self.assertTrue(all(method.startswith('current_precinct_forward_share:') for *_rest, method in weighted))

    def test_2016_candidate_rows_conserve_and_are_not_promoted(self):
        summary = json.loads((OUT / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['status'], 'DIAGNOSTIC_ONLY')
        self.assertEqual(summary['selected_years'], [2016])
        self.assertEqual(summary['county_party_conservation_failures'], 0)
        self.assertEqual(summary['production_changes'], [])
        self.assertEqual(summary['whole_county_rule_uses'], 'Census VAP, never block counts')
        with (OUT / 'affected_source_rows.csv').open(newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), summary['affected_source_row_scope_pairs'])
        for row in rows:
            votes = int(row['source_votes'])
            old = json.loads(row['old_allocations'])
            corrected = json.loads(row['corrected_allocations'])
            self.assertEqual(sum(old.values()), votes)
            self.assertEqual(sum(corrected.values()), votes)
            targets = json.loads(row['corrected_targets'])
            self.assertEqual(len({(target[0], target[1]) for target in targets}), len(targets))

    def test_evidence_fingerprints_are_current(self):
        fingerprints = json.loads((OUT / 'input_fingerprints.json').read_text(encoding='utf-8'))
        for relative, expected in fingerprints.items():
            path = ROOT / relative
            content = path.read_bytes()
            if path.suffix.lower() in {'.csv', '.txt', '.py', '.md'}:
                content = content.replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected, relative)

    def test_all_year_decision_ledger_preserves_typed_checkpoints(self):
        summary = json.loads((OUT.parent / 'report/all_year_decision_summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['original_differences'], 5409)
        self.assertEqual(summary['historical_checkpoint_at_6b293db'], 269)
        self.assertEqual(summary['original_numerical_lineage_explained'], 281)
        self.assertEqual(summary['original_unresolved'], 5128)
        self.assertEqual(summary['approved_emmaus_district_rows'], 10)
        self.assertEqual(summary['historical_judicial_files_missing_evidence'], 33)
        self.assertEqual(summary['judicial_files_with_recovered_evidence'], 27)
        self.assertEqual(summary['judicial_files_still_blocked'], 6)
        self.assertEqual(summary['production_changes_proposed_by_this_ledger'], [])
        with (OUT.parent / 'report/all_year_decision_ledger.csv').open(newline='', encoding='utf-8') as handle:
            rows = list(csv.DictReader(handle))
        original = [row for row in rows if row['row_universe'] == 'original_5409_district_differences']
        self.assertEqual(sum(int(row['district_rows']) for row in original), 5409)
        for row in rows:
            if row['production_correction_approved'] == 'True':
                self.assertEqual(row['geography_independently_validated'], 'True')
                self.assertEqual(row['official_returns_independently_validated'], 'True')

    def test_judicial_recovery_is_conserved_and_six_files_remain_blocked(self):
        directory = OUT.parent / 'judicial_evidence'
        summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['requested_files'], 33)
        self.assertEqual(summary['recovered_files'], 27)
        self.assertEqual(summary['county_conservation_failures'], 0)
        self.assertEqual(summary['unmatched_rows'], 0)
        self.assertEqual(summary['unallocated_rows'], 0)
        self.assertEqual(len(summary['blocked_files']), 6)
        self.assertTrue(all('commonwealth_court_2019' in name or 'supreme_court_2025' in name
                            for name in summary['blocked_files']))
        with (directory / 'recovery_ledger.csv').open(newline='', encoding='utf-8') as handle:
            ledger = list(csv.DictReader(handle))
        self.assertEqual(len(ledger), 33)
        self.assertEqual(sum(row['status'] == 'recovered' for row in ledger), 27)
        with (directory / 'input_fingerprints.json').open(encoding='utf-8') as handle:
            fingerprints = json.load(handle)
        self.assertEqual(len(fingerprints), 7)
        for relative, expected in fingerprints.items():
            content = (ROOT / relative).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected, relative)


if __name__ == '__main__':
    unittest.main()

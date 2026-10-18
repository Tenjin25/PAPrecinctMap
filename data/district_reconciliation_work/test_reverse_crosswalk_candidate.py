import csv
import copy
import hashlib
import json
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'Scripts')]
import build_pa_data_layers as layers
import build_rdh_2024_district_contests as rdh

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
            if path.suffix.lower() in {'.csv', '.json', '.txt', '.py', '.md'}:
                content = content.replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected, relative)

    def test_all_year_decision_ledger_preserves_typed_checkpoints(self):
        summary = json.loads((OUT.parent / 'report/all_year_decision_summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['original_differences'], 5409)
        self.assertEqual(summary['historical_checkpoint_at_6b293db'], 269)
        self.assertEqual(summary['original_numerical_lineage_explained'], 5409)
        self.assertEqual(summary['original_unresolved'], 0)
        self.assertEqual(summary['exact_official_rdh_stage_rows'], 1542)
        self.assertEqual(summary['exact_vest_2020_president_pipeline_rows'], 270)
        self.assertEqual(summary['exact_legacy_judicial_publication_replay_rows'], 3308)
        self.assertEqual(summary['exact_modern_publication_history_rows'], 62)
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

    def test_rdh_stage_replay_is_fail_closed_on_county_conservation(self):
        directory = OUT.parent / 'stage_lineage'
        summary = json.loads((directory / 'rdh_summary.json').read_text(encoding='utf-8'))
        fingerprints = json.loads((directory / 'rdh_input_fingerprints.json').read_text(encoding='utf-8'))
        for relative_path, expected in fingerprints['tracked_inputs'].items():
            content = (ROOT / relative_path).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected)
        self.assertEqual(
            fingerprints['supplied_archives']['2022']['sha256'],
            '6985775de9a8910d549a115186c412e0171c09bc79d9de128b055e962429d8a6',
        )
        self.assertEqual(
            fingerprints['supplied_archives']['2024']['sha256'],
            '47902c658648c242c64322ea3f446a1e9bd1038bd371c8642ea4df71ce7447d7',
        )
        self.assertEqual(summary['endpoint_rows'], 1890)
        self.assertEqual(summary['eligible_endpoint_rows'], 1890)
        self.assertEqual(summary['county_conserved_files'], 21)
        self.assertEqual(summary['county_blocked_files'], [])
        self.assertEqual(summary['county_conservation_failures'], 0)
        self.assertEqual(summary['integerization_district_change_rows'], 6)
        self.assertEqual(summary['integerization_county_increment_rows'], 147)
        stage = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
        self.assertEqual(stage['current_numerical_lineage_explained'], 5409)
        self.assertEqual(stage['unresolved_no_exact_stage_evidence'], 0)
        self.assertEqual(stage['exact_paths_using_official_rdh_rebuild'], 1542)
        self.assertEqual(stage['exact_paths_using_vest_2020_publication_pipeline'], 270)
        self.assertEqual(stage['exact_paths_using_legacy_judicial_publication_replay'], 3308)
        self.assertEqual(stage['exact_paths_using_modern_publication_history'], 62)
        with (directory / 'rdh_replay_endpoints.csv').open(newline='', encoding='utf-8') as handle:
            endpoints = list(csv.DictReader(handle))
        eligible = [row for row in endpoints if row['lineage_eligible'] == 'True']
        self.assertEqual(len(eligible), 1890)
        self.assertTrue(all(row['zero_unmatched_unallocated'] == 'True' for row in eligible))
        self.assertTrue(all(row['county_conservation_exact'] == 'True' for row in eligible))
        with (directory / 'rdh_integerization_district_changes.csv').open(newline='', encoding='utf-8') as handle:
            changes = list(csv.DictReader(handle))
        deltas = defaultdict(Counter)
        for row in changes:
            for field in ('dem_votes', 'rep_votes', 'other_votes', 'total_votes'):
                deltas[row['file']][field] += int(row[f'delta_{field}'])
        self.assertTrue(all(not any(file_delta.values()) for file_delta in deltas.values()))

    def test_county_local_integerization_is_deterministic_and_name_safe(self):
        allocations = defaultdict(lambda: defaultdict(Counter))
        allocations['A']['1'].update(dem_votes=4.4, total_votes=4.4)
        allocations['A']['2'].update(dem_votes=5.6, total_votes=5.6)
        allocations['B']['1'].update(dem_votes=2.5, total_votes=2.5)
        allocations['B']['2'].update(dem_votes=2.5, total_votes=2.5)
        sources = {'A': Counter(dem_votes=10, total_votes=10), 'B': Counter(dem_votes=5, total_votes=5)}
        results = {
            '1': {'dem_votes': 6.9, 'rep_votes': 0, 'other_votes': 0, 'total_votes': 6.9, 'dem_candidate': 'Candidate A'},
            '2': {'dem_votes': 8.1, 'rep_votes': 0, 'other_votes': 0, 'total_votes': 8.1, 'dem_candidate': 'Candidate A'},
        }
        first_allocations, first_results = copy.deepcopy(allocations), copy.deepcopy(results)
        second_allocations, second_results = copy.deepcopy(allocations), copy.deepcopy(results)
        rdh.integerize_county_district_allocations(first_allocations, sources, first_results)
        rdh.integerize_county_district_allocations(second_allocations, sources, second_results)
        self.assertEqual(first_allocations, second_allocations)
        self.assertEqual(first_results, second_results)
        self.assertEqual(first_results['1']['dem_votes'], 7)
        self.assertEqual(first_results['2']['dem_votes'], 8)
        self.assertEqual(first_results['1']['dem_candidate'], 'Candidate A')
        self.assertEqual(sum(first_allocations['A'][district]['dem_votes'] for district in ('1', '2')), 10)
        self.assertEqual(sum(first_allocations['B'][district]['dem_votes'] for district in ('1', '2')), 5)

    def test_vest_2020_pipeline_reproduces_all_published_rows(self):
        directory = OUT.parent / 'stage_lineage'
        summary = json.loads((directory / 'vest_2020_president_summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['endpoint_rows'], 270)
        self.assertEqual(summary['stage_rows'], 810)
        self.assertEqual(summary['source_counties'], 67)
        self.assertTrue(summary['zero_unmatched_source_vtds'])
        self.assertTrue(summary['zero_district_membership_gap_votes'])
        self.assertTrue(summary['all_published_votes_reproduced'])
        self.assertTrue(summary['candidate_names_preserved'])
        self.assertEqual(summary['source_statewide_party_totals']['total_votes'], 6918349)
        self.assertEqual(summary['certified_statewide_party_controls']['total_votes'], 6915283)
        fingerprints = json.loads((directory / 'vest_2020_president_input_fingerprints.json').read_text(encoding='utf-8'))
        self.assertEqual(
            fingerprints['supplied_archive']['sha256'],
            'f8c8bff158f06a8784d338b3a4642f2cc5463a398ae64d1a9c53ff89892c9eec',
        )
        for relative_path, expected in fingerprints['tracked_inputs'].items():
            content = (ROOT / relative_path).read_bytes().replace(b'\r\n', b'\n')
            self.assertEqual(hashlib.sha256(content).hexdigest(), expected)
        with (directory / 'vest_2020_president_endpoints.csv').open(newline='', encoding='utf-8') as handle:
            endpoints = list(csv.DictReader(handle))
        self.assertEqual(len(endpoints), 270)
        self.assertTrue(all(row['lineage_eligible'] == 'True' for row in endpoints))
        self.assertTrue(all(row['candidate_names_preserved'] == 'True' for row in endpoints))

    def test_legacy_judicial_pipeline_reproduces_all_published_rows(self):
        directory = OUT.parent / 'stage_lineage'
        summary = json.loads((directory / 'legacy_judicial_summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['endpoint_rows'], 3308)
        self.assertEqual(summary['publication_files'], 99)
        self.assertEqual(summary['contest_year_groups'], 33)
        self.assertEqual(summary['exact_numeric_rows'], 3308)
        self.assertEqual(summary['numeric_mismatches'], 0)
        self.assertEqual(summary['rows_with_legacy_candidate_names_equal'], 3223)
        self.assertEqual(summary['rows_requiring_name_preservation_stage'], 85)
        self.assertEqual(summary['label_field_changes'], 106)
        self.assertTrue(summary['current_files_equal_name_commit'])
        fingerprints = json.loads((directory / 'legacy_judicial_input_fingerprints.json').read_text(encoding='utf-8'))
        self.assertEqual(fingerprints['historical_commit'], '6f5f0fba26a60164cac6fceca0e9f8693d6fb8a3')
        self.assertEqual(fingerprints['candidate_name_commit'], '2afe1f6d4751093be19210136f13be8037c893cf')
        self.assertEqual(
            fingerprints['audit_script_lf_sha256'],
            hashlib.sha256((OUT.parent / 'audit_legacy_judicial_lineage.py').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
        )
        with (directory / 'legacy_judicial_endpoints.csv').open(newline='', encoding='utf-8') as handle:
            endpoints = list(csv.DictReader(handle))
        self.assertEqual(len(endpoints), 3308)
        self.assertTrue(all(row['lineage_eligible'] == 'True' for row in endpoints))
        self.assertTrue(all(row['candidate_names_preserved_by_name_commit'] == 'True' for row in endpoints))

    def test_modern_publication_history_closes_final_rows(self):
        directory = OUT.parent / 'stage_lineage'
        summary = json.loads((directory / 'modern_publication_summary.json').read_text(encoding='utf-8'))
        self.assertEqual(summary['target_rows'], 62)
        self.assertEqual(summary['endpoint_rows'], 62)
        self.assertEqual(summary['directed_stage_rows'], 179)
        self.assertEqual(summary['final_numeric_mismatches'], 0)
        self.assertTrue(summary['candidate_names_preserved'])
        self.assertEqual(summary['rows_by_year'], {'2022': 4, '2024': 58})
        with (directory / 'modern_publication_target_rows.csv').open(newline='', encoding='utf-8-sig') as handle:
            targets = list(csv.DictReader(handle))
        with (directory / 'modern_publication_endpoints.csv').open(newline='', encoding='utf-8') as handle:
            endpoints = list(csv.DictReader(handle))
        with (directory / 'modern_publication_stage_ledger.csv').open(newline='', encoding='utf-8') as handle:
            stages = list(csv.DictReader(handle))
        self.assertEqual(len(targets), 62)
        self.assertEqual(len(endpoints), 62)
        self.assertEqual(len(stages), 179)
        self.assertTrue(all(row['lineage_eligible'] == 'True' for row in endpoints))
        self.assertTrue(all(row['candidate_names_preserved'] == 'True' for row in endpoints))
        fingerprints = json.loads((directory / 'modern_publication_input_fingerprints.json').read_text(encoding='utf-8'))
        self.assertEqual(
            fingerprints['audit_script_lf_sha256'],
            hashlib.sha256((OUT.parent / 'audit_modern_publication_history.py').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),
        )

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

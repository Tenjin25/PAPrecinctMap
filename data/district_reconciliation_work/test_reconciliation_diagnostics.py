"""Evidence checks independent of the slow all-year rebuild."""
import csv
import hashlib
import json
import unittest
from collections import defaultdict
from pathlib import Path

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[1]
FIELDS = ('dem_votes', 'rep_votes', 'other_votes')


class EvidenceTests(unittest.TestCase):
    def test_westmoreland_certification_stage_replay(self):
        directory = WORK / 'certification_stages_2018'
        summary = json.loads((directory / 'westmoreland_replay_summary.json').read_text())
        self.assertEqual(summary['unmatched_rows'], 0)
        self.assertEqual(summary['production_changes'], [])
        exact = [r for r in summary['variant_results'] if r['model'] in
                 ('controlled_integerized_rows', 'uncontrolled_integerized_rows')]
        self.assertEqual(len(exact), 6)
        self.assertTrue(all(r['absolute_vote_mismatch'] == 0 for r in exact))
        # A different integerization stage is not silently accepted as equivalent.
        alternative = [r for r in summary['variant_results'] if r['model'] == 'uncontrolled_fractional_county_integerized']
        self.assertEqual([r['absolute_vote_mismatch'] for r in alternative], [2, 16, 14])
        with (directory / 'westmoreland_variant_comparison.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                self.assertEqual(int(row['reconstructed_district_votes']), int(row['replayed_westmoreland_votes']) + int(row['unchanged_other_counties_votes']))
                if row['model'] != 'uncontrolled_fractional_county_integerized':
                    self.assertEqual(int(row['delta']), 0)
                    self.assertEqual(row['reconstructed_district_votes'], row['target_district_votes'])
        allocated, source_votes = defaultdict(int), {}
        with (directory / 'westmoreland_source_row_allocations.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                key = row['model'], row['source_csv_row'], row['scope']
                allocated[key] += int(row['allocated_votes'])
                if key in source_votes:
                    self.assertEqual(source_votes[key], int(row['source_votes']))
                source_votes[key] = int(row['source_votes'])
        self.assertEqual(dict(allocated), source_votes)
        with (directory / 'westmoreland_variant_conservation.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                self.assertEqual(int(row['allocated_votes']), int(row['source_or_control_votes']))
        with (directory / 'district_party_stage_ledger.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 810)
        for row in rows:
            self.assertEqual(int(row['published']), int(row['retained_post_dra']) + int(row['localized_certification_delta']))
            self.assertEqual(int(row['candidate_minus_published']), -int(row['dra_delta']) + int(row['non_dra_stage_difference']))
        residuals = [r for r in rows if int(r['non_dra_stage_difference'])]
        self.assertEqual(len(residuals), 27)
        self.assertEqual(len({(r['scope'], r['district']) for r in residuals}), 11)
        with (WORK / 'report/verified_calibration_causes.csv').open(newline='') as handle:
            explained = [r for r in csv.DictReader(handle) if r['status'] == 'fully_explained_calibration_and_certification_order']
        self.assertEqual(len(explained), 11)
        for row in explained:
            for field in (*FIELDS, 'total_votes'):
                self.assertEqual(int(row[f'observed_{field}_delta']), int(row[f'calibration_{field}_delta']) + int(row[f'certification_order_{field}_delta']))
                self.assertEqual(int(row[f'unresolved_{field}_delta']), 0)

    def test_priority_official_source_benchmarks_and_incomplete_slice_guard(self):
        directory = WORK / 'priority_counties_raw_years'
        with (directory / 'priority_district_source_completeness.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 55)
        self.assertEqual(sum(row['status'].startswith('source_complete') for row in rows), 24)
        expected = {(2016, 'us_senate', 'state_house', '134'): (13544, 8865, 974),
                    (2018, 'governor', 'state_house', '95'): (11262, 4609, 297),
                    (2018, 'us_senate', 'congressional', '10'): (144159, 142310, 5901)}
        for identity, votes in expected.items():
            row = next(row for row in rows if (int(row['year']), row['contest'], row['scope'], row['district']) == identity)
            self.assertTrue(row['status'].startswith('source_complete'))
            self.assertEqual(row['unmatched_scope_rows_in_own_counties'], '0')
            self.assertEqual(row['all_own_counties_match_certified_source_controls'], 'True')
            self.assertEqual(tuple(int(row[f'raw_original_blocks_{field}']) for field in FIELDS), votes)
        incomplete = next(row for row in rows if (row['year'], row['contest'], row['scope'], row['district']) == ('2020', 'auditor', 'state_house', '95'))
        self.assertFalse(incomplete['status'].startswith('source_complete'))
        self.assertEqual(incomplete['all_own_counties_match_certified_source_controls'], 'False')

    def test_localized_rdh_identifiers_are_not_collapsed(self):
        from audit_priority_counties_raw_years import normalized
        self.assertNotEqual(normalized('045', 'SPRINGFIELD W 3 P 02(161)'), normalized('045', 'SPRINGFIELD W 3 P 02(165)'))
        self.assertNotEqual(normalized('133', 'YORK W 5 P 3 (Cong. 10)'), normalized('133', 'YORK W 5 P 3 (Cong. 11)'))
        self.assertEqual(normalized('045', 'SPRINGFIELD W 3 P 02(161)'), normalized('045', 'SPRINGFIELD 3-2 (HD 161)'))
        summaries = json.loads((WORK / 'priority_counties_raw_years/summary.json').read_text())
        self.assertTrue(all(not row['normalized_rdh_collisions'] for row in summaries))

    def test_all_year_original_blocks_conserve_source_not_assumed_certified(self):
        directory = WORK / 'original_block_years'
        summaries = json.loads((directory / 'summary.json').read_text())
        self.assertEqual([row['year'] for row in summaries], [2016, 2018, 2020])
        for summary in summaries:
            self.assertEqual(summary['block_universe'], 336985)
            self.assertEqual(summary['unallocated_entries'], 0)
            self.assertEqual(summary['county_conservation_failure_rows'], 0)
            with (directory / f'{summary["year"]}_county_district_party_cents.csv').open(newline='') as handle:
                allocated = defaultdict(int)
                for row in csv.DictReader(handle):
                    allocated[tuple(row[field] for field in ('model', 'scope', 'countyfp', 'contest', 'party_bucket'))] += int(row['modeled_vote_cents'])
            with (directory / f'{summary["year"]}_county_conservation.csv').open(newline='') as handle:
                for row in csv.DictReader(handle):
                    key = tuple(row[field] for field in ('model', 'scope', 'countyfp', 'contest', 'party_bucket'))
                    self.assertEqual(allocated[key], int(row['source_vote_cents']))
                    self.assertEqual(int(row['unallocated_vote_cents']), 0)
        review = json.loads((directory / 'review_summary.json').read_text())
        self.assertEqual(review['unique_year_contest_scope_district_rows'], 2970)
        self.assertGreater(review['source_control_differences_exceeding_one_vote'], 0)
        self.assertEqual(review['production_changes'], [])

    def test_three_official_2018_counties_conserve_in_every_scope(self):
        directory = WORK / 'benchmark_counties_all_scopes_2018'
        summary = json.loads((directory / 'summary.json').read_text())
        self.assertEqual(summary['unresolved_rows'], 0)
        self.assertEqual(summary['county_party_conservation_failures'], 0)
        with (directory / 'county_party_conservation.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 27)
        self.assertTrue(all(int(row['unallocated_votes']) == 0 for row in rows))
        with (directory / 'county_district_differences.csv').open(newline='') as handle:
            differences = list(csv.DictReader(handle))
        self.assertEqual(len(differences), 68)
        paired = defaultdict(int)
        for row in differences:
            paired[(row['scope'], row['county'], row['party_bucket'])] += int(row['direct_minus_normalized'])
        self.assertTrue(all(value == 0 for value in paired.values()))

    def test_original_block_pa10_models_and_controls(self):
        directory = WORK / 'pa10_original_blocks'
        summary = json.loads((directory / 'summary.json').read_text())
        self.assertEqual(summary['archive_sha256'], 'f88c1dc9d7f638efdf069ac8a6adc8b3e55df636360ad81171cf2e11f9687316')
        self.assertEqual(summary['block_universe'], 336985)
        self.assertEqual(summary['benchmark_county_blocks'], 23773)
        self.assertEqual(summary['unmatched_rows'], 0)
        expected = {'dem_votes': 144159, 'rep_votes': 142310, 'other_votes': 5901}
        self.assertEqual(summary['district_totals']['census_vap'], expected)
        self.assertEqual(summary['district_totals']['vap_mod'], expected)
        with (directory / 'county_party_conservation.csv').open(newline='') as handle:
            controls = list(csv.DictReader(handle))
        self.assertEqual(len(controls), 18)
        self.assertTrue(all(int(row['delta']) == 0 for row in controls))
        with (directory / 'precinct_allocations.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 3512)
        for row in rows:
            self.assertEqual(sum(json.loads(row['all_district_allocations']).values()), int(row['source_votes']))
        expected_places = {'YORK W 13': ('YORK 13-1', '10'), 'YORK W 1 P 1': ('YORK TWP 1-1', '11'), 'YORK W 5 P 1': ('YORK TWP 5-1', '11')}
        for precinct, (identity, district) in expected_places.items():
            selected = [row for row in rows if row['countyfp'] == '133' and row['precinct'] == precinct]
            self.assertEqual(len(selected), 8)
            for row in selected:
                self.assertEqual(row['matched_rdh_precinct'], identity)
                self.assertEqual({key for key, value in json.loads(row['district_weights']).items() if value > 0}, {district})

    def test_original_blocks_precinct_differences_reconcile(self):
        with (WORK / 'pa10_original_blocks/precinct_path_differences.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len({row['precinct'] for row in rows}), 5)
        for field, expected in zip(FIELDS, [-529, -1012, -25]):
            self.assertEqual(sum(int(row['direct_minus_bridge']) for row in rows if row['party_bucket'] == field), expected)

    def test_raw_pa10_source_and_allocations_conserve(self):
        summary = json.loads((WORK / 'pa10_raw_returns/summary.json').read_text())
        source_path = ROOT / Path(summary['source'].replace('\\', '/'))
        canonical = source_path.read_bytes().replace(b'\r\n', b'\n')
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), summary['source_lf_sha256'])
        self.assertEqual(summary['source_lf_sha256'], 'a05eaf5062c9caa6e2c2142b228d6cf5eb45c17386be5efd32cf1b9ad3c7cfc6')
        self.assertEqual(summary['unmatched_rows'], 0)
        self.assertEqual(summary['precincts'], 439)
        totals = defaultdict(lambda: dict.fromkeys(FIELDS, 0))
        with (WORK / 'pa10_raw_returns/source_precinct_allocation.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1756)
        for row in rows:
            allocations = json.loads(row['all_district_allocations'])
            self.assertEqual(sum(allocations.values()), int(row['source_votes']))
            totals[row['countyfp']][row['party_bucket']] += int(row['source_votes'])
        controls = {}
        with (ROOT / 'data/benchmarks/pa_county_2018_us_senate_certified.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                fp = {'CUMBERLAND': '041', 'DAUPHIN': '043', 'YORK': '133'}.get(row['county'].upper())
                if fp:
                    controls[fp] = {field: int(row[field]) for field in FIELDS}
        self.assertEqual(dict(totals), controls)
        self.assertEqual(summary['source_county_votes'], controls)
        self.assertEqual(summary['current_cd10_county_votes']['043'], controls['043'])

    def test_lehigh_transfers_conserve_and_reproduce_published_baseline(self):
        directory = WORK / 'lehigh_2016'
        summary = json.loads((directory / 'summary.json').read_text())
        self.assertEqual(summary['county_party_conservation_failures'], 0)
        self.assertTrue(all(row['all_published_district_party_values_reproduced'] for row in summary['publication_checks']))
        with (directory / 'county_district_path_comparison.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        totals = defaultdict(int)
        for row in rows:
            totals[(row['contest'], row['party_bucket'])] += int(row['total_delta'])
            self.assertEqual(int(row['source_path_delta']) + int(row['geography_path_delta']), int(row['total_delta']))
        self.assertTrue(all(value == 0 for value in totals.values()))
        senate = {row['party_bucket']: int(row['total_delta']) for row in rows
                  if row['district'] == '134' and row['contest'] == 'us_senate'}
        self.assertEqual([senate[field] for field in FIELDS], [1306, 1562, 127])
        self.assertEqual(summary['production_changes'], [])

    def test_lehigh_normalization_reproduces_and_retains_original_precincts(self):
        directory = WORK / 'lehigh_2016'
        summary = json.loads((directory / 'normalization_replay_summary.json').read_text())
        # Candidate spelling is tracked separately from geographic/vote equality.
        self.assertFalse(summary['exact_stored_row_multiset_reproduced'])
        self.assertGreater(summary['stored_only_rows'], 0)
        self.assertTrue(summary['stored_vote_geography_multiset_reproduced'])
        self.assertEqual(summary['baseline_county_district_party_mismatches'], 0)
        self.assertEqual(summary['crosswalk_metadata']['unmatched_rows'], 0)
        with (directory / 'normalization_precinct_district_effects.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        senate = [r for r in rows if r['contest'] == 'us_senate']
        for field, expected in zip(FIELDS, [1306, 1562, 127]):
            self.assertEqual(sum(int(r['direct_minus_replay']) for r in senate
                                 if r['district'] == '134' and r['party_bucket'] == field), expected)
        emmaus = {r['party_bucket']: int(r['direct_minus_replay']) for r in senate
                  if r['original_precinct'] == 'EMMAUS D 3' and r['district'] == '134'}
        self.assertEqual([emmaus[f] for f in FIELDS], [306, 376, 42])

    def test_hybrid_preview_has_no_unmatched_or_calibration_shortcut(self):
        directory = WORK / 'hybrid_review'
        with (directory / 'county_slice_review.csv').open(newline='') as handle:
            slices = list(csv.DictReader(handle))
        eligible = [r for r in slices if r['status'] == 'conserved_preview_geographic_review_required']
        self.assertEqual(len(slices), 198)
        self.assertEqual(len(eligible), 69)
        for row in eligible:
            self.assertEqual(row['unmatched_rows'], '0')
            for key in ('baseline_reproduces_all_published_districts', 'source_controls_exact', 'county_party_conservation_exact'):
                self.assertEqual(row[key], 'True')
        with (directory / 'county_district_party_transfers.csv').open(newline='') as handle:
            transfers = list(csv.DictReader(handle))
        grouped = defaultdict(int)
        for row in transfers:
            grouped[tuple(row[k] for k in ('year', 'contest', 'scope', 'county', 'party_bucket'))] += int(row['delta'])
        self.assertTrue(all(v == 0 for v in grouped.values()))
        with (directory / 'conservation_audit.csv').open(newline='') as handle:
            for row in csv.DictReader(handle):
                self.assertEqual(set(json.loads(row['statewide_party_delta']).values()), {0})
        summary = json.loads((directory / 'summary.json').read_text())
        self.assertEqual(summary['changed_district_rows'], 143)
        self.assertEqual(summary['production_changes'], [])

    def test_reverse_exposure_is_not_an_adjudicated_vote_delta(self):
        directory = WORK / 'reverse_crosswalk_exposure'
        summary = json.loads((directory / 'summary.json').read_text())
        self.assertEqual(summary['cross_boundary_key_scope_pairs'], 121)
        self.assertEqual(summary['keys_by_scope'], {'congressional': 14, 'state_house': 81, 'state_senate': 26})
        self.assertEqual(summary['counties'], 23)
        with (directory / 'year_contest_scope_county_exposure.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertTrue(all(r['status'] == 'exposure_only_not_a_vote_delta' for r in rows))

    def test_hd134_official_unit_membership_is_independent_of_modeled_slivers(self):
        from benchmark_hd134_legal_membership import membership
        self.assertTrue(membership('EMMAUS D 3', '6'))
        self.assertTrue(membership('SALISBURY W 4 D 1', '4'))
        self.assertTrue(membership('ALLENTOWN W 11 D 3', '2'))
        self.assertFalse(membership('ALLENTOWN W 11 D 2', '2'))
        self.assertFalse(membership('UPPER MILFORD D EASTERN', '4'))
        with self.assertRaises(ValueError):
            membership('ALLENTOWN W 11', '2')
        directory = WORK / 'hd134_legal_membership'
        with (directory / 'benchmark_comparison.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 11)
        senate = next(r for r in rows if r['year'] == '2016' and r['contest'] == 'us_senate')
        self.assertEqual([int(senate[f'legal_membership_{f}']) for f in FIELDS], [13548, 8872, 974])
        self.assertEqual(senate['county_source_controls_exact'], 'True')
        blocked = [r for r in rows if r['county_source_controls_exact'] == 'False']
        self.assertEqual({(r['year'], r['contest']) for r in blocked},
                         {('2020', c) for c in ('attorney_general', 'auditor', 'treasurer')})

    def test_calibration_explanations_are_exact_and_not_county_imputations(self):
        with (WORK / 'report/verified_calibration_causes.csv').open(newline='') as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 5409)
        explained = [row for row in rows if row['status'] == 'fully_explained_calibration']
        self.assertEqual(len(explained), 258)
        for row in explained:
            self.assertEqual(row['candidate_equals_precalibration'], 'True')
            self.assertEqual(row['published_equals_postcalibration'], 'True')
            for field in (*FIELDS, 'total_votes'):
                self.assertEqual(int(row[f'observed_{field}_delta']), int(row[f'calibration_{field}_delta']))
                self.assertEqual(int(row[f'unresolved_{field}_delta']), 0)
        pa10 = next(row for row in explained if row['file'] == 'congressional_us_senate_2018.json' and row['district'] == '10')
        self.assertEqual([int(pa10[f'observed_{field}_delta']) for field in FIELDS], [-281, 196, -7])


if __name__ == '__main__':
    unittest.main()

"""Fail-closed regression tests for the narrow Emmaus correction."""
import copy
import csv
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'Scripts'))
import reviewed_precinct_corrections as reviewed
import build_reviewed_release as release


class ReviewedCorrectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.review = json.loads((ROOT / 'data/benchmarks/reviewed_emmaus_2016.json').read_text())

    def baseline(self, entry):
        payload = json.loads((ROOT / 'data/district_contests' / entry['file']).read_text())
        if reviewed.vote_hash(payload) == entry['corrected_vote_hash']:
            for transfer in entry['transfers']:
                field = transfer['party_bucket']
                for district in set(transfer['before']) | set(transfer['after']):
                    payload['general']['results'][district][field] -= transfer['after'].get(district, 0) - transfer['before'].get(district, 0)
            for district in ('131', '134'):
                reviewed.finalize(payload['general']['results'][district])
            payload['meta'].pop('reviewed_precinct_corrections', None)
            payload['meta']['county_conservation_audit'] = copy.deepcopy(entry['baseline_county_audit'])
        self.assertEqual(reviewed.vote_hash(payload), entry['baseline_vote_hash'])
        return payload

    def test_all_five_reviews_are_exact_conserved_and_idempotent(self):
        self.assertEqual(len(self.review['entries']), 5)
        for entry in self.review['entries']:
            payload = self.baseline(entry)
            before = copy.deepcopy(payload)
            self.assertTrue(reviewed.apply_reviewed_correction(payload, self.review, ROOT))
            self.assertEqual(reviewed.vote_hash(payload), entry['corrected_vote_hash'])
            self.assertFalse(reviewed.apply_reviewed_correction(payload, self.review, ROOT))
            changed = []
            for district, row in payload['general']['results'].items():
                old = before['general']['results'][district]
                self.assertEqual([row[k] for k in ('dem_candidate', 'rep_candidate')], [old[k] for k in ('dem_candidate', 'rep_candidate')])
                if row != old:
                    changed.append(district)
            self.assertEqual(set(changed), {'131', '134'})
            for field in reviewed.FIELDS:
                self.assertEqual(sum(r[field] for r in before['general']['results'].values()),
                                 sum(r[field] for r in payload['general']['results'].values()))
            reviewed.verify_counties(payload, payload['meta']['county_conservation_audit'])

    def test_changed_source_rejects_before_any_mutation(self):
        payload = self.baseline(self.review['entries'][0])
        before = copy.deepcopy(payload)
        with patch.object(reviewed, 'source_hash', return_value='tampered'):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                reviewed.apply_reviewed_correction(payload, self.review, ROOT)
        self.assertEqual(payload, before)

    def test_changed_baseline_or_unmatched_rows_reject(self):
        for defect in ('votes', 'unmatched', 'county'):
            with self.subTest(defect=defect):
                payload = self.baseline(self.review['entries'][0])
                if defect == 'votes':
                    payload['general']['results']['1']['dem_votes'] += 1
                elif defect == 'unmatched':
                    payload['meta']['allocation_audit']['unmatched_rows'] = 1
                else:
                    payload['meta']['county_conservation_audit'] = copy.deepcopy(self.review['entries'][0]['baseline_county_audit'])
                    payload['meta']['county_conservation_audit']['counties']['LEHIGH']['district_allocations']['134']['dem_votes'] += 1
                before = copy.deepcopy(payload)
                with self.assertRaises(ValueError):
                    reviewed.apply_reviewed_correction(payload, self.review, ROOT)
                self.assertEqual(payload, before)

    def test_duplicate_transfer_or_residual_cannot_be_applied(self):
        for defect in ('duplicate', 'residual', 'outside'):
            review = copy.deepcopy(self.review)
            transfer = review['entries'][0]['transfers'][0]
            if defect == 'duplicate':
                review['entries'][0]['transfers'].append(copy.deepcopy(transfer))
            elif defect == 'residual':
                transfer['after']['134'] += 1
            else:
                transfer['after'] = {'131': transfer['official_votes']}
            # Reconstruct the real baseline before introducing a tampered review.
            payload = self.baseline(self.review['entries'][0])
            before = copy.deepcopy(payload)
            with self.assertRaises(ValueError):
                reviewed.apply_reviewed_correction(payload, review, ROOT)
            self.assertEqual(payload, before)

    def test_other_years_scopes_and_contests_are_untouched(self):
        payload = self.baseline(self.review['entries'][0])
        for key, value in [('year', 2018), ('scope', 'congressional'), ('contest_type', 'governor')]:
            other = copy.deepcopy(payload)
            other[key] = value
            before = copy.deepcopy(other)
            self.assertFalse(reviewed.apply_reviewed_correction(other, self.review, ROOT))
            self.assertEqual(other, before)

    def test_original_official_candidate_rows_and_all_block_assignments(self):
        directory = ROOT / 'data/district_reconciliation_work/emmaus_review'
        with (directory / 'official_candidate_rows.csv').open(newline='') as handle:
            ledger = list(csv.DictReader(handle))
        expected = {int(row['source_line']): row for row in ledger}
        self.assertEqual(len(expected), 108)
        seen = set()
        with (ROOT / 'data/ElectionReturns_2016_General_PrecinctReturns.txt').open(newline='', encoding='utf-8-sig') as handle:
            for line, parts in enumerate(csv.reader(handle), 1):
                if line in expected:
                    row = expected[line]
                    self.assertEqual(parts[19:21], ['6', 'EMMAUS'])
                    self.assertEqual(' '.join(p for p in parts[20:25] if p).strip(), row['precinct'])
                    self.assertEqual(int(parts[15]), int(row['votes']))
                    self.assertEqual(' '.join(parts[11:15]).strip(), row['candidate'])
                    seen.add(line)
        self.assertEqual(seen, set(expected))
        for entry in self.review['entries']:
            for transfer in entry['transfers']:
                votes = sum(int(r['votes']) for r in ledger if
                            (r['contest'], r['precinct'], r['party_bucket']) ==
                            (entry['contest_type'], transfer['precinct'], transfer['party_bucket']))
                self.assertEqual(transfer['official_votes'], votes)
        with (ROOT / 'data/42_PA_SLDL22.txt').open(newline='') as handle:
            assignments = {r['GEOID']: str(int(r['SLDLST'])) for r in csv.DictReader(handle)}
        with (directory / 'original_precinct_block_witness.csv').open(newline='') as handle:
            witness = list(csv.DictReader(handle))
        self.assertEqual(len(witness), 401)
        self.assertEqual(len({r['rdh_2016_precinct'] for r in witness}), 6)
        self.assertTrue(all(assignments[r['block']] == r['current_house'] == '134' for r in witness))

    def test_release_rejects_unrelated_candidate_edits(self):
        entry = self.review['entries'][0]
        before = self.baseline(entry)
        after = copy.deepcopy(before)
        reviewed.apply_reviewed_correction(after, self.review, ROOT)
        self.assertEqual(set(release.validate_pair(before, after, entry, self.review)), {'131', '134'})
        after['general']['results']['1']['dem_candidate'] = 'Wrong candidate'
        with self.assertRaises(ValueError):
            release.validate_pair(before, after, entry, self.review)


if __name__ == '__main__':
    unittest.main()

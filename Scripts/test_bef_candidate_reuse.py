"""Reject incomplete, stale, or altered acceptance candidates."""
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_bef_candidate as candidate


class ReuseTests(unittest.TestCase):
    def test_raw_county_lookup_uses_configured_case_correct_data_root(self):
        builder = candidate.import_builder()
        with tempfile.TemporaryDirectory(dir=candidate.ROOT) as temporary:
            data = Path(temporary) / 'data'
            data.mkdir()
            (data / 'pa_counties.geojson').write_text(json.dumps({'features': [
                {'properties': {'COUNTYFP20': '077', 'NAME20': 'Lehigh'}}]}))
            with patch.object(builder, 'data_dir', data), patch.object(builder, 'RAW_COUNTY_NAME_BY_FIPS', None):
                self.assertEqual(builder.raw_county_name_lookup(), {'077': 'Lehigh'})

    def test_reviewed_transitive_witnesses_invalidate_reuse_and_cannot_escape(self):
        with tempfile.TemporaryDirectory(dir=candidate.ROOT) as temporary:
            root = Path(temporary)
            data = root / 'data'
            (data / 'benchmarks').mkdir(parents=True)
            witness = data / 'district_reconciliation_work/witness.csv'
            witness.parent.mkdir()
            witness.write_text('precinct,district\nEmmaus,134\n')
            review = data / 'benchmarks/reviewed_fixture.json'
            review.write_text(json.dumps({'input_hashes': {'data/district_reconciliation_work/witness.csv': 'fixture'}}))
            vap, baf = data / 'vap.gz', data / 'baf.zip'
            vap.write_bytes(b'vap')
            baf.write_bytes(b'baf')
            with patch.object(candidate, 'ROOT', root), patch.object(candidate, 'DATA', data):
                before = candidate.input_fingerprints(vap, baf)
                self.assertIn(str(witness.resolve()), before)
                witness.write_text('precinct,district\nEmmaus,131\n')
                after = candidate.input_fingerprints(vap, baf)
                self.assertNotEqual(before[str(witness.resolve())], after[str(witness.resolve())])
                witness.unlink()
                self.assertNotIn(str(witness.resolve()), candidate.input_fingerprints(vap, baf))
                review.write_text(json.dumps({'input_hashes': {'../outside.csv': 'fixture'}}))
                with self.assertRaisesRegex(ValueError, 'escapes workspace'):
                    candidate.input_fingerprints(vap, baf)

    def test_official_luzerne_bounds_reject_impossible_conserved_candidate(self):
        fixture = json.loads((candidate.DATA / "benchmarks/luzerne_2024_senate_precinct_bounds.json").read_text())
        county = {"8": {"dem_votes": 57754, "rep_votes": 71270, "other_votes": 2980}}
        county["9"] = {field: total - county["8"][field] for field, total in fixture["county_votes"].items()}
        payload = {key: fixture[key] for key in ("year", "contest_type", "scope")}
        payload["meta"] = {"county_conservation_audit": {"counties": {"LUZERNE": {"district_allocations": county}}}}
        failures = candidate.verify_geographic_bounds(payload)
        self.assertEqual(len(failures), 6)  # excess in CD8, corresponding deficit in CD9
        self.assertEqual([row["candidate"] - row["maximum"] for row in failures[:3]], [62, 554, 1])
        for field, fixed in fixture["fixed_votes"]["8"].items():
            county["8"][field] = fixed + round(fixture["pooled_votes"][field] * 403 / 1390)
            county["9"][field] = fixture["county_votes"][field] - county["8"][field]
        self.assertEqual(candidate.verify_geographic_bounds(payload), [])
        del county["9"]
        self.assertEqual(len(candidate.verify_geographic_bounds(payload)), 3)
        payload["year"] = 2018
        self.assertEqual(candidate.verify_geographic_bounds(payload), [])

    def test_retention_rebuild_conserves_yes_no_and_keeps_other_year_manifest(self):
        builder = candidate.import_builder()
        contest = "commonwealth_court_retention_anne_covey"
        rows = [{"county": "ADAMS", "precinct": "A",
                 "office": "Commonwealth Court Retention - Anne Covey", "party": party,
                 "candidate": party.title(), "votes": str(votes)} for party, votes in (("YES", 60), ("NO", 40))]
        maps = {scope: {("001", "000001"): {"1": 100}} for scope in candidate.clustered.SCOPES}
        with tempfile.TemporaryDirectory(dir=candidate.ROOT) as temporary:
            directory = Path(temporary)
            existing = [{"scope": scope, "contest_type": contest, "year": year,
                         "file": f"{scope}_{contest}_{year}.json"}
                        for scope in maps for year in (2018, 2090)]
            (directory / "manifest.json").write_text(json.dumps({"files": existing}))
            with patch.object(builder, "data_dir", directory), \
                 patch.object(builder, "iter_openelections_csvs", return_value=[(2090, directory / "returns.csv")]), \
                 patch.object(builder, "read_csv_rows", return_value=rows), \
                 patch.object(builder, "apply_official_county_party_controls", side_effect=lambda values, *a, **kw: values), \
                 patch.object(builder, "county_fips_by_name", return_value={"ADAMS": "001"}), \
                 patch.object(builder, "load_vtd_current_district_blocks", return_value=maps), \
                 patch.object(builder, "maintained_targets_for_row", return_value=[("001", "000001", 1, "fixture")]):
                builder.build_district_manifests(directory, contest_types={contest}, years={2090})
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual({(row["scope"], row["year"]) for row in manifest["files"]},
                             {(scope, year) for scope in maps for year in (2018, 2090)})
            for scope in maps:
                payload = json.loads((directory / f"{scope}_{contest}_2090.json").read_text())
                self.assertEqual(candidate.verify_county_evidence(payload), [])
                self.assertEqual(payload["meta"]["county_conservation_audit"]["counties"]["ADAMS"]["source"],
                                 {"dem_votes": 60, "rep_votes": 40, "other_votes": 0, "total_votes": 100})

    def test_forged_county_pass_flag_does_not_hide_inconsistent_votes(self):
        row = {"dem_votes": 40, "rep_votes": 60, "other_votes": 0, "total_votes": 100}
        payload = {"meta": {"county_conservation_audit": {"all_counties_conserved": True,
                   "counties": {"COUNTY": {"source": row, "allocated": row,
                   "district_allocations": {"1": row}}}}}, "general": {"results": {"1": dict(row)}}}
        self.assertEqual(candidate.verify_county_evidence(payload), [])
        payload["general"]["results"]["1"]["rep_votes"] += 1
        self.assertTrue(candidate.verify_county_evidence(payload))
        self.assertTrue(candidate.verify_county_evidence({}))

    def test_only_changed_source_years_are_rebuilt(self):
        source = str(candidate.DATA / "Openelections/2018/returns.csv")
        other = str(candidate.DATA / "benchmarks/pa_county_2024_us_senate_certified.csv")
        self.assertEqual(candidate.changed_source_years({source: "old"}, {source: "new"}), {2018})
        self.assertEqual(candidate.changed_source_years({source: "same"}, {source: "same", other: "added"}), {2024})
        self.assertEqual(candidate.changed_source_years({source: "removed"}, {}), {2018})
        self.assertEqual(candidate.changed_source_years({source: "same"}, {source: "same"}), set())

    def test_geography_code_and_publication_changes_rebuild_all_years(self):
        for path in (candidate.DATA / "42_PA_CD118.txt", candidate.ROOT / "build_pa_data_layers.py",
                     candidate.PUBLISHED / "congressional_us_senate_2018.json"):
            self.assertIsNone(candidate.changed_source_years({str(path): "old"}, {str(path): "new"}))

    def test_unsigned_publication_copy_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=candidate.ROOT) as temporary:
            directory = Path(temporary)
            (directory / "manifest.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "Unsigned"):
                candidate.validate_reuse(directory, {})

    def test_receipt_requires_matching_inputs_and_outputs(self):
        with tempfile.TemporaryDirectory(dir=candidate.ROOT) as temporary:
            directory = Path(temporary)
            output = directory / "congressional_us_senate_2024.json"
            output.write_text('{"votes": 100}')
            inputs = {"source": "original"}
            (directory / candidate.RECEIPT).write_text(json.dumps({
                "version": 1, "inputs": inputs,
                "outputs": candidate.candidate_fingerprints(directory),
            }))
            candidate.validate_reuse(directory, inputs)
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                candidate.validate_reuse(directory, {"source": "changed"})
            output.write_text('{"votes": 101}')
            with self.assertRaisesRegex(ValueError, "outputs changed"):
                candidate.validate_reuse(directory, inputs)


if __name__ == "__main__":
    unittest.main()

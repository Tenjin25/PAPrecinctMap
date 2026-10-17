"""Exercise cold, warm, and year-selective acceptance through the real builder."""
import csv
import io
import json
import sys
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_bef_candidate as acceptance


class AcceptanceLifecycleTests(unittest.TestCase):
    def test_completed_cold_warm_and_changed_year_reuse(self):
        fixture = json.loads((acceptance.DATA / 'benchmarks/luzerne_2024_senate_precinct_bounds.json').read_text())
        builder = acceptance.import_builder()
        contest = 'commonwealth_court_retention_anne_covey'
        maps = {scope: {('001', '000001'): {'1': 100}} for scope in acceptance.clustered.SCOPES}
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as temporary, ExitStack() as stack:
            root = Path(temporary)
            data, published, out = root / 'data', root / 'data/district_contests', root / 'data/candidate'
            published.mkdir(parents=True)
            (data / 'benchmarks').mkdir()
            (data / 'benchmarks/luzerne_2024_senate_precinct_bounds.json').write_text(json.dumps(fixture))
            paths = {}
            def write_source(year, yes):
                path = data / f'Openelections/{year}/returns.csv'
                path.parent.mkdir(parents=True, exist_ok=True)
                rows = [{'county': 'ADAMS', 'precinct': 'A', 'office': 'Commonwealth Court Retention - Anne Covey',
                         'candidate': party.title(), 'party': party, 'votes': str(votes)}
                        for party, votes in [('YES', yes), ('NO', 100 - yes)]]
                with path.open('w', newline='') as handle:
                    writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                    writer.writeheader()
                    writer.writerows(rows)
                paths[year] = path
            write_source(2090, 60)
            write_source(2092, 70)
            stack.enter_context(patch.object(builder, 'data_dir', data))
            stack.enter_context(patch.object(builder, 'iter_openelections_csvs', side_effect=lambda: sorted(paths.items())))
            stack.enter_context(patch.object(builder, 'apply_official_county_party_controls', side_effect=lambda rows, *a, **kw: rows))
            stack.enter_context(patch.object(builder, 'county_fips_by_name', return_value={'ADAMS': '001'}))
            stack.enter_context(patch.object(builder, 'load_vtd_current_district_blocks', return_value=maps))
            stack.enter_context(patch.object(builder, 'maintained_targets_for_row', return_value=[('001', '000001', 1, 'fixture')]))
            builder.build_district_manifests(published, contest_types={contest})
            stack.enter_context(patch.object(acceptance, 'ROOT', root))
            stack.enter_context(patch.object(acceptance, 'DATA', data))
            stack.enter_context(patch.object(acceptance, 'PUBLISHED', published))
            stack.enter_context(patch.object(acceptance, 'import_builder', return_value=builder))
            stack.enter_context(patch.object(acceptance.clustered, 'build_vap_maps', return_value=(maps, {}, 1, 1)))
            stack.enter_context(patch.object(acceptance, 'input_fingerprints', side_effect=lambda *a: {str(path.resolve()): acceptance.digest(path) for path in paths.values()}))
            build = stack.enter_context(patch.object(builder, 'build_district_manifests', wraps=builder.build_district_manifests))
            def run(*flags):
                with patch.object(sys, 'argv', ['build_bef_candidate.py', '--out-dir', str(out), '--quiet', *flags]), redirect_stdout(io.StringIO()):
                    return acceptance.main()
            self.assertEqual(run(), 0)
            self.assertEqual(build.call_count, 1)
            cold = acceptance.candidate_fingerprints(out)
            self.assertEqual(run('--reuse'), 0)
            self.assertEqual(run('--incremental'), 0)
            self.assertEqual(build.call_count, 1)
            self.assertEqual(acceptance.candidate_fingerprints(out), cold)
            write_source(2090, 65)
            self.assertEqual(run('--incremental'), 2)  # changed votes remain blocked, not silently accepted
            self.assertEqual(build.call_count, 2)
            self.assertEqual(build.call_args.kwargs['years'], {2090})
            after = acceptance.candidate_fingerprints(out)
            for filename, digest in cold.items():
                if filename.endswith('_2092.json'):
                    self.assertEqual(after[filename], digest)
            for scope in maps:
                payload = json.loads((out / f'{scope}_{contest}_2090.json').read_text())
                self.assertEqual(acceptance.verify_county_evidence(payload), [])
                self.assertEqual(payload['general']['results']['1']['dem_votes'], 65)
            report = json.loads((out / 'acceptance_report.json').read_text())
            self.assertEqual(report['counts']['district_vote_changes'], 3)
            self.assertEqual(report['counts']['county_conservation_failures'], 0)
            self.assertEqual(report['counts']['files_with_unmatched_or_unallocated_rows'], 0)
            manifest = json.loads((out / 'manifest.json').read_text())
            self.assertEqual(len(manifest['files']), 6)


if __name__ == '__main__':
    unittest.main()

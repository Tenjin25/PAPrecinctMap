"""Independently cold-rebuild every 2016 statewide layer through production."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Scripts'))
import build_bef_candidate as acceptance

WORK = Path(__file__).resolve().parent


def main():
    out = WORK / 'reviewed_year_rebuild'
    if out.exists():
        raise ValueError('Use a fresh isolated reviewed-year directory')
    out.mkdir()
    builder = acceptance.import_builder()
    maps, _, _, _ = acceptance.clustered.build_vap_maps(ROOT / 'data/crosswalks/pa_block20_vap.csv.gz', ROOT / 'data/BlockAssign_ST42_PA.zip')
    builder.VTD_CURRENT_DISTRICT_BLOCKS = maps
    builder.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    original = builder.read_csv_rows
    cache = {}
    def integerized(path):
        key = str(path)
        if key not in cache:
            cache[key] = acceptance.clustered.integerize_fractional_rows(original(path))
        return cache[key]
    builder.read_csv_rows = integerized
    builder.apply_dra_share_calibration = lambda *args: None
    builder.build_district_manifests(out, contest_types={'president', 'us_senate', 'attorney_general', 'auditor', 'treasurer'}, years={2016})
    acceptance.restore_candidate_labels(out, acceptance.capture_candidate_labels(ROOT / 'data/district_contests'))
    checked = []
    for path in out.glob('*.json'):
        if path.name == 'manifest.json':
            continue
        payload = json.loads(path.read_text())
        published = json.loads((ROOT / 'data/district_contests' / path.name).read_text())
        assert payload['general']['results'] == published['general']['results'], path.name
        assert acceptance.verify_county_evidence(payload) == [], path.name
        audit = payload['meta']['allocation_audit']
        assert audit['unmatched_rows'] == audit['unallocated_rows'] == 0
        checked.append(path.name)
    assert len(checked) == 15
    summary = {'status': 'PASS', 'cold_rebuilt_layers': sorted(checked), 'all_published_district_votes_and_names_reproduced': True,
               'all_county_party_allocations_independently_verified': True, 'unmatched_or_unallocated_rows': 0,
               'production_writes': False}
    (WORK / 'report/reviewed_year_rebuild.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

"""Build one typed decision ledger without conflating overlapping row universes."""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path(__file__).resolve().parent
OUT = WORK / 'report/all_year_decision_ledger.csv'

FIELDS = [
    'record_type', 'row_universe', 'year', 'contest', 'scope', 'county', 'cause',
    'decision_class', 'district_rows', 'source_rows', 'numerical_lineage_explained',
    'geography_independently_validated', 'official_returns_independently_validated',
    'production_correction_approved', 'publication_retained', 'blocker', 'evidence',
    'evidence_lf_sha256',
]


def digest(path: Path) -> str:
    content = path.read_bytes().replace(b'\r\n', b'\n')
    return hashlib.sha256(content).hexdigest()


def base_row(**values):
    row = {field: '' for field in FIELDS}
    row.update(values)
    return row


def main():
    rows = []
    baseline_path = WORK / 'stage_lineage/district_stage_paths.csv'
    baseline_groups = Counter()
    with baseline_path.open(newline='', encoding='utf-8') as handle:
        for item in csv.DictReader(handle):
            explained = item['decision_class'] == 'numerical_lineage_explained'
            county = (
                '129/Westmoreland (certification component only)'
                if item['status'] == 'exact_replayed_dra_and_certification_order'
                else 'not attributable from retained district stage'
            )
            cause = item['stage_path'] or 'unresolved'
            baseline_groups[(item['year'], item['contest'], item['scope'], county, cause, item['status'], explained)] += 1
    for (year, contest, scope, county, cause, status, explained), count in sorted(baseline_groups.items()):
        rows.append(base_row(
                record_type='district_difference_decision',
                row_universe='original_5409_district_differences',
                year=year, contest=contest, scope=scope,
                county=county, cause=cause,
                decision_class='numerical_lineage_explained' if explained else 'unresolved_or_publication_retained',
                district_rows=count, source_rows=0,
                numerical_lineage_explained=explained,
                geography_independently_validated=False,
                official_returns_independently_validated=(
                    status == 'exact_replayed_dra_and_certification_order'
                ),
                production_correction_approved=False, publication_retained=True,
                blocker=(
                    'numerical lineage is not independent geographic validation'
                    if explained else 'no exact retained stage evidence'
                ),
                evidence='stage_lineage/district_stage_paths.csv',
                evidence_lf_sha256=digest(baseline_path),
        ))

    reverse_path = WORK / 'reverse_crosswalk_candidate/decision_ledger.csv'
    with reverse_path.open(newline='', encoding='utf-8') as handle:
        for item in csv.DictReader(handle):
            rows.append(base_row(
                record_type='candidate_mechanism_decision',
                row_universe='2016_actual_reverse_fallback_candidate',
                year=item['year'], contest=item['contest'], scope=item['scope'], county=item['county'],
                cause=item['cause'], decision_class=item['decision_class'],
                district_rows=item['affected_district_rows'], source_rows=item['affected_source_rows'],
                numerical_lineage_explained=True,
                geography_independently_validated=False,
                official_returns_independently_validated=True,
                production_correction_approved=False, publication_retained=True,
                blocker='forward share is numerical evidence, not independent fragment geography',
                evidence='reverse_crosswalk_candidate/affected_source_rows.csv',
                evidence_lf_sha256=digest(WORK / 'reverse_crosswalk_candidate/affected_source_rows.csv'),
            ))

    review_path = ROOT / 'data/benchmarks/reviewed_emmaus_2016.json'
    review = json.loads(review_path.read_text(encoding='utf-8'))
    for entry in review['entries']:
        rows.append(base_row(
            record_type='approved_production_correction',
            row_universe='reviewed_emmaus_release',
            year=2016, contest=entry['contest_type'], scope='state_house', county='077/Lehigh',
            cause='reverse_many_to_many_crosswalk_full_vtd_union',
            decision_class='production_correction_approved_and_verified', district_rows=2,
            source_rows=len(entry['transfers']), numerical_lineage_explained=True,
            geography_independently_validated=True,
            official_returns_independently_validated=True,
            production_correction_approved=True, publication_retained=False, blocker='',
            evidence='data/benchmarks/reviewed_emmaus_2016.json',
            evidence_lf_sha256=digest(review_path),
        ))

    acceptance_path = WORK / 'report/acceptance_integration.json'
    acceptance = json.loads(acceptance_path.read_text(encoding='utf-8'))
    recovery_path = WORK / 'judicial_evidence/recovery_ledger.csv'
    recovery = {}
    if recovery_path.exists():
        with recovery_path.open(newline='', encoding='utf-8') as handle:
            recovery = {row['file']: row for row in csv.DictReader(handle)}
    missing = defaultdict(lambda: Counter())
    for item in acceptance['missing_county_evidence_files']:
        scope = item['file'].split('_', 1)[0] if not item['file'].startswith('state_') else '_'.join(item['file'].split('_')[:2])
        status = 'recovered' if recovery.get(item['file'], {}).get('status') == 'recovered' else 'remaining'
        missing[(item['year'], item['contest'], scope)][status] += 1
    for (year, contest, scope), status_counts in sorted(missing.items()):
        recovered = status_counts['recovered']
        remaining = status_counts['remaining']
        rows.append(base_row(
            record_type='evidence_gate', row_universe='legacy_judicial_missing_evidence_files',
            year=year, contest=contest, scope=scope,
            county='all retained official-source counties' if recovered else 'not recovered',
            cause='official judicial county/allocation evidence recovery' if recovered else 'missing county/allocation evidence',
            decision_class='independently_validated_evidence' if recovered else 'remaining_blocker',
            district_rows=0, source_rows=0, numerical_lineage_explained=False,
            geography_independently_validated=False,
            official_returns_independently_validated=bool(recovered),
            production_correction_approved=False, publication_retained=True,
            blocker=(
                f'{remaining} file still lacks retained official contest rows'
                if remaining else 'historical evidence gate recovered; production remains unapproved'
            ),
            evidence=(
                'judicial_evidence/recovery_ledger.csv'
                if recovered else 'report/acceptance_integration.json'
            ),
            evidence_lf_sha256=digest(recovery_path) if recovered else digest(acceptance_path),
        ))

    benchmark_path = WORK / 'report/benchmarks.csv'
    benchmark_hash = digest(benchmark_path)
    rows.extend([
        base_row(
            record_type='permanent_acceptance_benchmark', row_universe='benchmark_decisions',
            year=2024, contest='us_senate', scope='congressional', county='079/Luzerne',
            cause='official precinct geographic bounds', decision_class='publication_retained_with_evidence',
            district_rows=1, source_rows=0, numerical_lineage_explained=True,
            geography_independently_validated=True, official_returns_independently_validated=True,
            production_correction_approved=False, publication_retained=True,
            blocker='generic candidate violates official Luzerne bounds',
            evidence='report/benchmarks.csv; official_luzerne_2024/', evidence_lf_sha256=benchmark_hash,
        ),
        base_row(
            record_type='permanent_acceptance_benchmark', row_universe='benchmark_decisions',
            year=2018, contest='us_senate', scope='congressional', county='Cumberland/Dauphin/York',
            cause='official precinct identity plus original block assignments',
            decision_class='publication_retained_with_evidence', district_rows=1, source_rows=0,
            numerical_lineage_explained=True, geography_independently_validated=True,
            official_returns_independently_validated=True, production_correction_approved=False,
            publication_retained=True,
            blocker='pre-calibration geographic delta cannot be layered onto calibrated publication',
            evidence='pa10_original_blocks/EVIDENCE.md; pa10_raw_returns/EVIDENCE.md',
            evidence_lf_sha256=digest(WORK / 'pa10_original_blocks/EVIDENCE.md'),
        ),
    ])

    rows.sort(key=lambda row: (
        int(row['year']), row['contest'], row['scope'], row['county'], row['record_type'], row['cause']
    ))
    with OUT.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    original = [row for row in rows if row['row_universe'] == 'original_5409_district_differences']
    counts = Counter()
    for row in original:
        count = int(row['district_rows'])
        counts['original_differences'] += count
        if str(row['numerical_lineage_explained']) == 'True':
            counts['original_numerical_lineage_explained'] += count
        else:
            counts['original_unresolved'] += count
    summary = {
        **counts,
        'historical_checkpoint_at_6b293db': 269,
        'new_exact_county_clustered_stage_rows': 12,
        'exact_official_rdh_stage_rows': sum(
            int(row['district_rows']) for row in original
            if 'official_rdh_return_rebuild' in row['cause']
        ),
        'approved_emmaus_district_rows': sum(int(row['district_rows']) for row in rows if row['row_universe'] == 'reviewed_emmaus_release'),
        'historical_judicial_files_missing_evidence': len(acceptance['missing_county_evidence_files']),
        'judicial_files_with_recovered_evidence': sum(row.get('status') == 'recovered' for row in recovery.values()),
        'judicial_files_still_blocked': sum(row.get('status') != 'recovered' for row in recovery.values()),
        'reverse_candidate_decision_groups': sum(row['row_universe'] == '2016_actual_reverse_fallback_candidate' for row in rows),
        'permanent_acceptance_benchmarks': 2,
        'production_changes_proposed_by_this_ledger': [],
    }
    if summary['original_differences'] != 5409 or summary['historical_checkpoint_at_6b293db'] != 269:
        raise RuntimeError(f'Historical checkpoint mismatch: {summary}')
    (WORK / 'report/all_year_decision_summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()

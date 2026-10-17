# Reviewed production release: 2016 Emmaus

## Decision and exact scope

Promote only the source-backed transfer from HD-131 to HD-134 for Emmaus
precincts in the five 2016 statewide contests. Ten district rows in five House
files change. Every other production vote value is retained, including 2024
Senate PA-08 and 2018 Senate PA-10. The generic all-year Carter/VAP replacement
and the 143-row diagnostic hybrid preview are **not promoted**.

The individually enumerated before/after rows are in
`../emmaus_review/proposed_district_changes.csv`. The following quantities move
from HD-131 to HD-134; they are not new votes or statewide residuals:

| 2016 contest | Democratic | Republican | Other |
| --- | ---: | ---: | ---: |
| Attorney General | 951 | 937 | 0 |
| Auditor General | 820 | 901 | 134 |
| President | 904 | 974 | 89 |
| Treasurer | 866 | 854 | 136 |
| U.S. Senate | 853 | 1,015 | 92 |

The resulting HD-134 Senate votes are 13,091 Democratic, 8,318 Republican,
939 other, 22,348 total. This is a deliberately narrow hybrid, not the generic
block-model or full administrative-membership benchmark. Other Lehigh precinct
questions are not silently folded into the correction.

## Why this correction is stronger than the published path

The [official current House district description](https://www.pa.gov/agencies/vote/resources/redistricting/pennsylvania-redistricting-house-of-representative)
places the whole of Emmaus Borough in HD-134. The original 2016 RDH assignment
independently places all 401 Emmaus blocks from all six precincts in current
HD-134 using the official BEF. The original official returns identify Emmaus
as a borough, so this correction does not depend on a same-name township alias
or the historical continuity of a partially included ward.

The retained 108 original candidate rows supply the votes; modeled RDH block
vote quantities are not used as ballot counts. The normalization replay
reproduces every stored Lehigh vote/geography row and every baseline
county/district/party allocation. It isolates the error: reversing a
many-to-many VTD crosswalk uses full VTD VAP and drops forward fractional
contributions. Parts of Emmaus precincts 3, 5, and 6 are consequently assigned
to HD-131. Each source precinct's before/after allocation is retained in the
review fixture. No inverse-share renormalization or margin fitting is used.

## Gates and reproducibility

`Scripts/reviewed_precinct_corrections.py` binds the complete baseline layer,
source/control/crosswalk hashes, original block witness, official candidate
rows, and exact corrected district votes. Unexpected source changes, a new
baseline, county-attribution changes, duplicate transfers, residual votes,
unmatched rows, missing receipts, or unrelated output changes fail closed.
Application is idempotent and production rebuilds retain the review.

Rebuild receipts also fingerprint the review's transitive witness inputs, not
only the review JSON. Editing or deleting a witness invalidates reuse; paths
outside the workspace are rejected. The county lookup now uses the configured,
case-correct data directory, with a regression test for Linux-safe rebuilding.

`Scripts/build_reviewed_release.py` constructs an isolated release, proves
all unreviewed files byte-identical, validates all 67 certified county-party
controls for each changed layer, preserves candidate labels verbatim, and
requires explicit promotion. Original files are retained locally and any
filesystem error triggers rollback. `Scripts/audit_reviewed_precinct_corrections.py`
and the CI workflow recheck the published review and all source hashes.

The cachebuster is `2026-10-16-emmaus-precinct-v13`. The release report,
post-release cold/warm acceptance evidence, and test/audit results are retained
beside this document. Large user-supplied RDH ZIPs and transient full rebuild
directories are not committed.

The production suite passes 52 tests. A separate cold run rebuilds all 15
2016 statewide-contest layers and reproduces every published district vote and
candidate name with zero unmatched rows and independently checked county-party
evidence. Full cold/warm results are recorded in `post_release_acceptance.json`;
they must keep the broad candidate blocked rather than waive its failures.

The completed final cold run binds 609 input files and 268 output files.
All five reviewed House layers reproduce the release exactly; 228 statewide
layers independently pass county-party arithmetic checks. Warm `--reuse` and
unchanged `--incremental` checks take 6.07 and 6.72 seconds respectively, retain
every output/difference-ledger hash, and retain all broad-candidate blockers.

## Explicitly unresolved / retained

- The original 5,409 differences are not all adjudicated. Exact retained
  calibration evidence fully explains 258; 11 more have partial calibration
  lineage, and 5,140 lack exact calibration-stage evidence.
- PA-08's generic candidate violates official Luzerne precinct bounds. Retain
  publication, including the pooled Butler 5 VAP split.
- PA-10's original-precinct model is near the published margin, but replacing
  a calibrated layer requires whole-layer source/county attribution. No
  district residual is shifted to another district to force agreement.
- The 121 reverse-crosswalk key/scope exposures in 23 counties are screening
  findings, not 121 proven vote errors. Full source-path adjudication is needed.
- Thirty-three legacy judicial slices lack county/allocation evidence; this
  is not a demonstrated arithmetic error and does not justify invented metadata.
- Failed 2020 source controls, unmatched localized rows, historical geography,
  and the Salisbury block-model sliver remain explicit blockers for broader
  changes. Only the Emmaus proof is promoted.

# All retained district-stage lineage replay

This diagnostic treats every retained adjustment CSV as a directed old-to-new
edge and searches for an exact candidate-to-publication path for each of the
original 5,409 differing district rows. It does not infer causes from residual
size, margin similarity, or an undirected match.

Twenty-two ledgers provide 24,468 retained stage rows. Exact directed paths are
found for 5,398 district rows: 258 through the known 2018 Senate DRA ledgers,
12 through `county_clustered_district_changes.csv`, and 1,488 through exact
official RDH rebuild endpoints (344 of those then pass through the retained
county-clustered stage), 270 through the complete VEST 2020 President
publication pipeline, and 3,308 through the Carter-adjusted historical judicial
publication replay, and 62 through the retained 2022/2024 publication-history
chain. The separately reproduced Westmoreland
certification-order stage explains 11 more rows, so the current combined
numerical-lineage count is all 5,409 original differences and the unresolved
numerical-lineage count is zero.

The 12 county-clustered rows are House 133 and 183 in 2022 statewide contests,
House 133 in four 2024 statewide contests, and Senate 30 in four 2024 statewide
contests. The RDH replay rebuilds all 21 retained 2022/2024 scope-contest files
from the supplied official archives. County-local deterministic largest
remainder now preserves every county-party control and derives district totals
from those same integer cells; all 21 files have zero unmatched/unallocated
rows and exact county-party conservation. The corrected integerization changes
only six district rows from the former statewide rounding endpoints, as paired
one-vote transfers. `district_stage_paths.csv` contains exact before/after vote
vectors, ledger row numbers, and normalized fingerprints.

The 2020 President replay uses the same fingerprinted VEST archive for both
vote-bearing precinct identities and historical precinct geometry. It then
replays the retained congressional benchmark or legislative DRA shares, the
archive-source statewide control, and the retained certified statewide control.
All 270 published rows and candidate names reproduce exactly with zero unmatched
precincts and zero district-membership-gap votes. County totals are retained for
the pre-calibration source; no post-control county attribution is inferred.

The judicial replay runs the detached historical builder at `6f5f0fb` with its
retained Carter block-to-VTD equivalency and current-line BEF assignments. It
reproduces all 3,308 differing judicial rows in 99 files exactly. Of those,
3,223 already have identical candidate labels; the remaining 85 rows are tied
to the later name-preservation commit `2afe1f6` (106 label-field changes), whose
judicial files are byte-identical to current publication. This proves historical
numerical lineage only. The modern official-source rebuild and its six missing
county/allocation evidence files remain separate acceptance decisions.

The last 62 rows are four 2022 U.S. Senate rows and 58 2024 President rows.
Their exact directed chains start at the retained historical RDH endpoints and,
where applicable, traverse VAP control, localized residual allocation,
county-clustering, and certified county-reconciliation commits. A clean replay
from the currently supplied archives is not equivalent to those historical
stages and is not used as proof. The commit-to-commit ledger terminates exactly
at current publication for every row and preserves every candidate name.

These are numerical lineage decisions only. District-stage ledgers do not
provide county components or independently validate geography, and this batch
does not approve a production correction.

Reproduce:

    python data/district_reconciliation_work/audit_rdh_stage_lineage.py --source-2022 PATH --source-2024 PATH
    python data/district_reconciliation_work/audit_vest_2020_president_lineage.py --source PATH
    python data/district_reconciliation_work/audit_legacy_judicial_lineage.py --historical-worktree PATH --rebuild
    python data/district_reconciliation_work/audit_modern_publication_history.py
    python data/district_reconciliation_work/audit_all_stage_lineage.py
    python data/district_reconciliation_work/build_all_year_decision_ledger.py

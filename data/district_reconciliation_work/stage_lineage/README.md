# All retained district-stage lineage replay

This diagnostic treats every retained adjustment CSV as a directed old-to-new
edge and searches for an exact candidate-to-publication path for each of the
original 5,409 differing district rows. It does not infer causes from residual
size, margin similarity, or an undirected match.

Seventeen ledgers provide 18,759 retained stage rows. Exact directed paths are
found for 270 district rows: 258 through the known 2018 Senate DRA ledgers and
12 through `county_clustered_district_changes.csv`. The separately reproduced
Westmoreland certification-order stage explains 11 more rows, so the current
combined numerical-lineage count is 281 and the unresolved count is 5,128.

The 12 newly recognized rows are House 133 and 183 in 2022 statewide contests,
House 133 in four 2024 statewide contests, and Senate 30 in four 2024 statewide
contests. `district_stage_paths.csv` contains exact before/after vote vectors,
ledger row numbers, and normalized fingerprints.

These are numerical lineage decisions only. District-stage ledgers do not
provide county components or independently validate geography, and this batch
does not approve a production correction.

Reproduce:

    python data/district_reconciliation_work/audit_all_stage_lineage.py
    python data/district_reconciliation_work/build_all_year_decision_ledger.py

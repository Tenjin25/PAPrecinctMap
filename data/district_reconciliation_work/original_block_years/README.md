# All current districts: original 2016, 2018, and 2020 blocks

This is a **diagnostic comparison, not a production replacement**. The user
provided all three original RDH block archives in the main checkout's `data`
directory. Their SHA-256 checksums and column definitions are in `summary.json`.
The scripts read them in place and do not commit the large ZIPs.

Coverage: all 336,985 blocks in each year, all 17 current congressional
districts, all 203 current State House districts, and all 50 current State
Senate districts. Eleven year/contest combinations produce 2,970 distinct
year/contest/scope/district comparisons (8,910 rows across three models).

Models:

- `rdh_block`: the original RDH block-disaggregated vote values as supplied.
- `census_vap`: the same RDH election-precinct source vote totals redistributed
  directly over their original assigned blocks using retained Census block VAP.
- `vap_mod`: those same precinct totals redistributed with original VAP_MOD.

The latter two share the VAP-based whole-county rule. A county classified as
whole is assigned intact; no block-count threshold is substituted for VAP.
No current VTD is used as an intermediate election-vote distribution unit.
All three models join through the retained **current-plan** BEFs, not the
election-era congressional or legislative district labels.

## Units and conservation

Values ending in `_cents` are **hundredths of a modeled vote**, not ballots.
The original block values are verified to be hundredth-unit values within
floating-point serialization tolerance; unexpected extra precision aborts.
The counterfactuals preserve the supplied source's hundredth-unit total by
largest remainder within each election precinct and party. They do not infer
original integer precinct vote counts from rounded block-disaggregated values.

All county-party source totals conserve exactly in every year, scope and
model. Zero source blocks are unmatched and zero entries are unallocated.
This is conservation of the **RDH source totals**, not a claim that those
totals equal certified returns.

`rdh_source_vs_certified_county_controls.csv` independently compares 2,211
year/contest/county/party totals with retained certified controls. There are
2,118 nonzero differences, including 524 larger than one vote. Some are
fractional disaggregation/rounding effects; others need original precinct and
official-return reconciliation. None is automatically classified as rounding,
redistributed statewide, or hidden by a source-total PASS flag.

## Review priorities, not proposed production changes

The complete list is `all_district_review_priorities.csv`. Notable comparisons:

| Year / contest | Current scope / district | Census-model minus published margin (percentage points) |
|---|---|---:|
| 2016 Senate | House 134 | -4.1962 |
| 2018 Governor | House 95 | +5.1450 |
| 2018 Governor | House 191 | +3.5678 |
| 2020 Auditor | House 95 | +4.9680 |
| 2020 Auditor | Senate 1 | -2.2914 |

These are signed Democratic-minus-Republican margins, not winner's absolute
margins. They are review priorities only. The largest Census-VAP-versus-VAP_MOD
margin difference anywhere in this comparison is about 0.034511 percentage
points (2018 Governor, House 94). Population weighting alone does not explain
the multi-percentage-point discrepancies listed above; precinct identity,
intermediate VTD allocation, calibration and source controls require review.

For a source-vote-confirmed example, `../pa10_original_blocks/` uses actual
official 2018 Senate precinct votes rather than rounded RDH block vote totals.
`../benchmark_counties_all_scopes_2018/` extends those same 1,756 official
candidate rows to all three legislative scopes in Cumberland, Dauphin and York.
All rows match and conserve certified county-party totals; 68 county/district/
party contributions differ from the normalized candidate. These are county-
reconciled diagnostic deltas, not a license to apply pre-calibration shifts
on top of already calibrated production values.

The official state/Census House whole-block versus fragment exception remains
documented in `../state_plan_sources/README.md`; these comparisons do not
invent a population split for that fragment.

Reproduce:

```
python data/district_reconciliation_work/audit_original_block_years.py
python data/district_reconciliation_work/summarize_original_block_years.py
python data/district_reconciliation_work/audit_2018_benchmark_counties_all_scopes.py
```

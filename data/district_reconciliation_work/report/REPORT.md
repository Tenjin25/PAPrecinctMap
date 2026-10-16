# Remaining district differences: verified baseline

Production recommendation: retain current values. No district changes proposed yet.

Completed baseline cold rebuild: 5,409 district rows differ; statewide party totals are unchanged and its audit reports zero unmatched/unallocated rows. Independent county-evidence checks fail in 54 retention files; do not treat the old county PASS flags as verification.

Official Luzerne precinct bounds reject the baseline 2024 Senate PA-08 candidate: it exceeds the maximum by 62 Democratic, 554 Republican, and 1 other vote. Retain the published PA-08 allocation; only pooled Butler Township District 5 requires a modeled VAP split. See ../official_luzerne_2024/EVIDENCE.md and the permanent Luzerne benchmark fixture.

| Scope | Changed rows |
|---|---:|
| congressional | 637 |
| state_house | 3,762 |
| state_senate | 1,010 |

The CSVs enumerate all differences and candidate county context. Causal reconciliation remains incomplete.

- Lineage labels identify documented method differences, not quantified causal decompositions.
- Published historical rows lack county attribution; assigning their district residual to candidate counties would fabricate evidence.
- 2018 DRA share agreement is not independent proof: published PA-10 was calibrated to that source.
- The Wikipedia 2018 district table must be checked for district vintage: Pennsylvania had 18 districts then, versus 17 current districts.
- Candidate uses original BAF ZIP, while source ledger labels the 17-block-adjusted CSV as its Carter input.
- RDH county metadata truncates fractional allocations before statewide district rounding; separate rounding attribution is required.
- The original acceptance --reuse accepted unsigned copied publication directories. The revised code requires a completed input/output receipt.
- 54 baseline candidate retention files put YES/NO into Other in their county metadata, despite displaying YES/NO in the two main columns. Their old county PASS flags are insufficient. The builder bookkeeping is corrected, and a new cold rebuild is required.
- Year-selective reuse and its manifest preservation are implemented and regression tested; a new signed cold run and warm-run integration check remain pending.

# Recommended handling of current-plan allocation differences

Production decision: promote only the reviewed 2016 Emmaus whole-borough
correction (HD-131 and HD-134, five contests). Retain every other published
vote value. See [report/RELEASE.md](report/RELEASE.md) and the source-bound
`data/benchmarks/reviewed_emmaus_2016.json` fixture. This is not a completed
causal classification of the 5,409-row ledger; the broad candidate is blocked.

## Source and allocation hierarchy

1. Start with retained official election returns, preserving election year,
   county, election precinct ID/name, candidate, party, ballot category, and
   source row number. Keep certified county-party totals as independent checks.
2. Use the official 2022 Carter congressional and LRC legislative assignments
   as the boundary authority. The Census whole-block BEFs agree on every
   common block assignment. Handle suffixed state fragments explicitly.
3. Match an election precinct to its own documented geographic vintage before
   using a Census VTD bridge. A synthetic frontend precinct ID is not itself
   an official election precinct. Keep every allocation weight and its origin.
4. Carry a county intact when one current district contains at least 99.9%
   of county block VAP. Model only genuinely split counties. Do not substitute
   block counts for VAP or apply global party shares after allocation.
5. Keep mail/absentee/provisional rows in their stated county and any explicitly
   identified district. Treat a county-local turnout allocation as modeled,
   not geographically observed. Preserve that distinction in the evidence.
6. Use deterministic largest-remainder integerization within the required
   source control group. Record fractional inputs, floors, remainder order,
   targets, and final integers. Require integer county contributions to sum
   to each district output as well as each county control.
7. Compare DRA/RDH outputs as alternate models unless their source rows and
   current-plan geography can be independently traced. A value calibrated to
   a DRA share cannot then be validated independently by the same DRA share.

## Known House fragment

The state originals put `421010257002008A` in House 200 and
`421010257002008B` in House 194. The Census BEF tabulates the parent in 194.
The parent has 40 VAP. Maintained VTD `(101,000904)` has 733 VAP and is wholly
in House 194 under the whole-block BEF. Thus at most 40/733 of this VTD's VAP
weight can move through this exception; the number of affected votes depends
on the source precinct's vote count and its complete allocation path.

Retain House 194 as the documented Census whole-block baseline. Calculate
sensitivity endpoints with 0 and 40 parent VAP assigned to House 200. Replace
that interval with a point allocation only when official fragment population
or other adequate population evidence establishes it. Fragment area alone
would introduce another model. Never equate 40 VAP with 40 ballots.

The downloaded adjusted-population Excel archive contains 9,178 VTD rows,
not block-fragment populations. It does not settle this exception.

## Benchmark implications

- PA-08 2024: the published county-clustered RDH path is reproducible exactly.
  The acceptance path reads previously disaggregated normalized returns,
  applies county-party integerization/control, and uses the Carter block map.
  Exact final block assignment does not make those source votes exact.
  Official Luzerne county precinct returns now independently support retaining
  the published PA-08 result. The CD8/CD9 House precinct lists overlap only at
  Butler Township District 5 (the township north of Hazleton). Its pooled
  Senate votes are 289 Democratic, 856 Republican, and 17 other; the House
  results establish a genuine split but do not observe Senate votes by fragment.
  The published Luzerne allocation equals the fixed CD8 precinct totals plus
  403/1390 of this pool, matching Carter block VAP. The generic candidate
  exceeds the maximum possible CD8 Luzerne allocation by 62 Democratic,
  554 Republican, and 1 other vote, even if the entire pool went to CD8.
  Reject that candidate for this benchmark. See
  `official_luzerne_2024/pa08_official_county_bounds.csv` and its reproducible
  `verify_pa08_bounds.py`. This supports the published allocation model, not
  a claim that the modeled split is an observed Senate fragment count.
- PA-10 2018: published totals arise from DRA-share calibration. The exact
  candidate precedes that calibration. The matching DRA result is not an
  independent check; Wikipedia's 2018 district table also requires a vintage
  check before comparison with the 17-district 2022 plan.
  The original precinct replay and a fresh official-source checksum check
  are now retained in `pa10_raw_returns/`. All 439 precincts / 1,756 named
  candidate rows match with exact three-county controls and zero unmatched
  votes. The replay gives Casey +0.464727%, but still uses a VAP_MOD-derived
  precinct bridge. Its difference from the normalized candidate is localized
  to +6 D, +7 R, and net zero Other; it does not explain the DRA margin.
  Current and 2018 Jackson precinct boundaries must not be assumed identical.
  No production change is justified yet.
  Follow-up after the user supplied the original 2018 block archive:
  `pa10_original_blocks/EVIDENCE.md` supersedes the VTD-bridge interpretation.
  Direct original election-precinct block assignments give Casey +0.632418%
  under both Census VAP and VAP_MOD, with zero unmatched rows and exact
  county-party conservation. Five York precincts explain the direct-versus-VTD
  bridge shift, including a city/township identity problem. Thus VAP_MOD itself
  is not this benchmark's cause. The calibrated publication still cannot be
  changed by shifting a district residual into another district; reconcile
  the whole layer's county attribution first.

`audit_calibration_causes.py` now verifies complete before/after numeric
evidence for 258 of the 5,409 district differences. Eleven more have a
documented calibration stage but unresolved additional differences; 5,140
have no exact calibration-stage evidence. These classifications do not impute
county components for district-level calibration deltas.

## Acceptance and release

The first baseline reports 5,409 differences and zero statewide total changes.
Independent recomputation found 54 retention files whose county metadata puts
YES/NO in Other while outputs use the two main columns. A bookkeeping fix and
regression test address this; a fresh candidate must pass the stronger checks.

Completion receipts fingerprint source inputs and output JSONs. Unsigned,
interrupted, changed, or stale candidates cannot be reused. Unchanged signed
years are reused when only another year's returns/control change; shared
geography, code, and publication changes invalidate all years. Every reused
output still runs through the acceptance checks.

`test_acceptance_lifecycle.py` passes a real-builder, controlled-input lifecycle
test: cold completion, unchanged `--reuse`, unchanged `--incremental`, and
changed-year-only rebuild. Unchanged-year files remain byte-identical, manifests
retain both years, changed district votes remain blocked, and county-party
conservation / zero unmatched checks still run. This is not a substitute for
the full-data cold/warm integration run.

The full-data run has now completed: `report/acceptance_integration.json`
records zero vote/name changes from the original cold baseline, all 54
retention metadata repairs, 228 independently verified statewide-contest
files, and 33 legacy judicial files missing county/allocation evidence.
There are no actual arithmetic failures among evidence-bearing files. Warm
reuse and unchanged incremental runs take about six seconds and retain every
output hash and all blocking checks. The new original-block comparisons and
official-source completeness checks are in `report/FOLLOWUP.md`; production
remains unchanged and no failed source controls are distributed statewide.

Before promotion, provide individual proposed district rows, source hashes,
the full vote-allocation path, exact county/statewide conservation, zero
unmatched rows, and reviewed candidate names. Until that evidence is complete,
retain production and publish only clearly labeled diagnostics and tests.

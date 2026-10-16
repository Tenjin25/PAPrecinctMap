# Recommended handling of current-plan allocation differences

Production decision at this checkpoint: retain all published district rows.
There are no proposed production vote changes yet. This is not a completed
causal classification of the 5,409-row ledger.

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

Before promotion, provide individual proposed district rows, source hashes,
the full vote-allocation path, exact county/statewide conservation, zero
unmatched rows, and reviewed candidate names. Until that evidence is complete,
retain production and publish only clearly labeled diagnostics and tests.

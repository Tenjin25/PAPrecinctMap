# Current district aggregation status

Updated: 2026-10-15

## Production decision

The published district vote files remain unchanged. They retain the reviewed
VAP-based county-cluster allocations, including the 2024 PA-08 and 2018 PA-10
Senate reconciliations. A generic BEF/BAF rebuild was not promoted.

The isolated rebuild conserved every statewide party total and every county
party total across congressional, State House, and State Senate outputs, with
zero unmatched or unallocated source rows and no file-coverage changes.
However, exact district-row comparison found 8,775 changed rows:

| Scope | Changed district rows |
|---|---:|
| Congressional | 725 |
| State House | 6,348 |
| State Senate | 1,702 |

Because those changes offset within statewide totals, a statewide-only gate
would have missed them. `Scripts/build_bef_candidate.py` now fails closed on
any district party/total change and writes the exhaustive changes to
`district_vote_changes.csv` in the candidate directory.

## Required production methodology

1. Use official/certified county party totals as the source control.
2. Carry counties with at least 99.9% of their 2020 block VAP in one district
   intact into that district.
3. Allocate only materially split counties through Carter BAF/VTD assignments,
   official BEFs, and block VAP.
4. Use maintained NHGIS historical block chains only where an exact reviewed
   precinct lineage exists.
5. Keep mail/provisional residuals inside their source county; never distribute
   an unexplained residual statewide.
6. Use largest-remainder integerization within the county/party allocation.
7. Require exact party and total conservation by county, statewide, and across
   all three district scopes.
8. Treat DRA shares as a diagnostic comparison, not a production calibration.

The 99.9% classification must use block VAP. Raw BEF block counts are not a
valid substitute: a test rebuild using counts increased, rather than reduced,
the district-row mismatch. Reproducing the production build therefore requires
the Pennsylvania 2020 PL block file (P0030001 voting-age population) or an
equivalent retained block-VAP artifact.

## Added safeguards

- County conservation metadata records source totals, allocated totals,
  district destinations, deltas, and allocation-quality vote buckets.
- The conservation audit validates every recorded county/party delta.
- Candidate acceptance checks inspect new files even when coverage differs.
- Candidate acceptance requires exact district-row equality, not merely equal
  statewide totals.
- Incremental builds cannot silently add files absent from the existing
  district manifest.
- Certified county controls with zero-valued minor-party placeholders use a
  documented county-local precinct-turnout fallback. This was required for the
  512-vote Jefferson County 2022 U.S. Senate Other total.

## Locked benchmark results

- 2024 U.S. Senate, PA-08: Casey 180,743; McCormick 198,221; Other 8,976;
  total 387,940; McCormick +4.505336%.
- 2018 U.S. Senate, PA-10: Casey 144,963; Barletta 143,119; Other 5,933;
  total 294,015; Casey +0.627179%.

These benchmarks and corrected candidate display names remain covered by the
county-cluster regression suite.

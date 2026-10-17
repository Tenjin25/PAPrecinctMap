# HD-134 independent official-description benchmark

The [Pennsylvania Department of State district description](https://www.pa.gov/agencies/vote/resources/redistricting/pennsylvania-redistricting-house-of-representative)
was reviewed on 2026-10-16. Its named municipality, ward, and division membership
is retained structurally in `evidence.json`. `benchmark_hd134_legal_membership.py`
selects original official named-candidate return rows using those administrative
units, without VAP, modeled block votes, district margins, or residual fitting.
School subrows remain separate but share their containing named ward/division.

For 2016 Senate the selected original votes are 13,548 Democratic, 8,872
Republican, and 974 other (23,394 total; Democratic margin 19.988031%). The
published values are 12,238 / 7,303 / 847. The original-precinct Census-VAP model
gives 13,544 / 8,865 / 974: it leaves 4 Democratic and 7 Republican votes from
Salisbury ward 4 division 1 in HD-131 even though the official description
includes the whole ward in HD-134. Therefore the block model is not itself an
exact administrative-membership benchmark.

All 11 available contests across 2016, 2018, and 2020 are listed in
`benchmark_comparison.csv`; every included original candidate/precinct row is
in `official_source_membership_ledger.csv`. County source controls are exact
for all 2016/2018 contests and 2020 President. The other three 2020 contests
retain source-control gaps and are blocked, not scaled.

This is a benchmark, not an authorized district transfer. The current official
description does not by itself prove historical ward/division boundary
continuity. That must be checked, and every neighboring-district counterpart
must be traced before promoting a narrowly corrected hybrid. No production
data or candidate names were changed.

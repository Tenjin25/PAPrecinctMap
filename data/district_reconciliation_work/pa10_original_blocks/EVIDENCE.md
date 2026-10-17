# PA-10: direct original election-precinct block assignments

This supersedes the VTD-bridge-only geographic interpretation in
`../pa10_raw_returns/EVIDENCE.md`. The earlier replay remains useful as a
separately quantified intermediate stage, not the preferred geography.

The user supplied `pa_2018_gen_2020_blocks.zip` in the main checkout's data
directory. It is read in place, not copied into the candidate's source tree.
SHA-256: `f88c1dc9d7f638efdf069ac8a6adc8b3e55df636360ad81171cf2e11f9687316`.
The archive contains exactly 336,985 distinct block IDs; every block matches
the retained BEF and Census VAP sources. The three benchmark counties contain
23,773 blocks.

Original official Senate precinct vote rows are joined directly to original
RDH election-precinct block assignments, preserving the official municipality
type. No current VTD is used as an intermediate vote-distribution unit.
Structural label matching is explicit and recorded. Township and city labels
are **not** merged: `YORK W 1 P 1` with municipality type 4 matches
`YORK TWP 1-1`, not York City Ward 1. Ward-only labels can resolve to a single
division 1 only when no other divisions exist. Explicit school/congressional
subrows are pooled only if their common original precinct lies wholly in one
current congressional district; the script asserts this condition.

## Results using official source votes

| County / variant | Democratic | Republican | Other |
|---|---:|---:|---:|
| Cumberland / direct blocks | 45,015 | 49,847 | 1,992 |
| Dauphin / direct blocks | 59,533 | 47,152 | 2,023 |
| York / direct blocks | 39,611 | 45,311 | 1,886 |
| PA-10 / direct blocks | 144,159 | 142,310 | 5,901 |
| PA-10 / published | 144,963 | 143,119 | 5,933 |

The direct result totals 292,370 named-candidate votes, Casey +0.632418%.
Both Census VAP and VAP_MOD produce exactly these same integer vote totals.
Both genuine split election precincts have identical population weights under
the two models: North Newton (CD10 847, CD13 1,036) and Jackson 1 (CD10 1,920,
CD11 1,102). **VAP_MOD is not the cause of the PA-10 discrepancy.**

All 1,756 official candidate rows match; zero unmatched rows/votes. Every
source row conserves its votes, and all three county-party controls match
exactly under both models. See `county_party_conservation.csv`.

## Exact source-precinct differences from the aggregated VTD bridge

| York election precinct | Democratic delta | Republican delta | Other delta |
|---|---:|---:|---:|
| Jackson P1 | -9 | -17 | -1 |
| Jackson P2 | +3 | +6 | 0 |
| York City Ward 13 | +316 | +45 | +8 |
| York Township 1-1 | -419 | -558 | -12 |
| York Township 5-1 | -420 | -488 | -20 |
| Total / direct minus VTD bridge | -529 | -1,012 | -25 |

The state's current-plan description independently puts all York City in
PA-10 and York Township in PA-11:
https://www.pa.gov/agencies/vote/resources/redistricting/pennsylvania-redistricting-us-congress
The supplied block assignments and retained BEF agree with these placements.
Jackson P2's original blocks are wholly PA-10; only Jackson P1 requires a
split. The five-precinct ledger includes source line numbers, candidate names,
official municipality types, original RDH identifiers, and allocation weights.

## Production decision and remaining scope

No production change yet. The direct result is geographically better supported
than the generic candidate, and supports a Casey margin near +0.63%, but its
absolute vote totals differ from the calibrated publication by -804 D, -809 R,
and -32 Other. The published DRA calibration has no county decomposition.
It would be invalid to subtract those votes from PA-10 and add them to PA-11
as an unexplained balancing residual. Reconcile the other current districts
and the county allocations before proposing a conserved replacement layer.

Original block-to-election-precinct assignments are still an RDH geographic
model, not observed Senate ballots by block. Do not label this an official
district tally. The original archive is not committed because it exceeds
GitHub's ordinary file-size limit; the compact benchmark tables and checksum
retain the evidence needed to review the specific placements.

Reproduce: `python data/district_reconciliation_work/reconcile_pa10_original_blocks.py [archive_path]`.

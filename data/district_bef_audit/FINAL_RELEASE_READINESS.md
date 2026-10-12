# Final BEF candidate release readiness

Audit finalized and locally promoted: 2026-10-11. No commit or push was made.

## Decision

**PROMOTED LOCALLY AFTER EXPLICIT USER APPROVAL.**

The exact Carter-BAF-to-BEF allocation method is now the published working-tree
method. Following explicit approval, 267 contest JSONs and their generated
manifest were copied from `data/district_bef_candidate` to
`data/district_contests`. The promoted files intentionally reproduce the
currently selected source returns rather than legacy totals embedded in the
former published files.

Post-promotion verification found 0 SHA-256 mismatches across all 268 copied
files, and `Scripts/audit_district_vote_conservation.py` passed against the
published directory.

## Mechanical gates

| Gate | Result |
|---|---|
| Carter/BEF 15-digit block join | PASS |
| Duplicate BEF block GEOIDs | PASS: 0 |
| Missing or extra BEF blocks | PASS: 0 |
| Invalid district IDs | PASS: 0 |
| Unexplained county mismatches | PASS: 0 (the 3 observed rows are the retained Carter cross-county adjustments) |
| Unmatched source rows | PASS: 0 |
| Unallocated source votes | PASS: 0 |
| Precinct/candidate vote conservation | PASS |
| Contest and statewide conservation | PASS |
| Published file coverage unchanged by the candidate builder | PASS |
| Published statewide totals reproduced | **FAIL: 227 files differ** |

The isolated candidate is in `data/district_bef_candidate`. Its acceptance
report records zero conservation failures, zero files with unmatched or
unallocated rows, and zero coverage changes.

## Provenance and mapping findings

- The Carter-adjusted artifact actually used is
  `data/crosswalks/pa_block20_to_vtd20.csv`, SHA-256
  `5999f2eb0fdaac5e92a61949f25db312bdd77a4bbf2f6199a1360fbaecbfd031`.
- Its repository vintage is commit
  `25b3846336371e27ebdb90a51792c9dc6d2958c5` (2026-09-08). Its upstream
  acquisition provenance is not retained, so a more specific Carter
  publication vintage cannot be proved from this workspace.
- It has the same 336,985-block universe as the December 11, 2020 VTD member
  in `BlockAssign_ST42_PA.zip`, with 17 Carter-adjusted assignments. The ZIP's
  CD/SLDL/SLDU members were not treated as 2022-line assignments.
- Each 2022-line BEF contains exactly 336,985 unique valid block assignments.
  The Carter join produces 14 split VTDs for Congress, 8 for State House, and
  4 for State Senate.
- The old overlay crosswalks contain 107 non-census A/B fragment keys in place
  of 53 real blocks. Current raw old-to-BEF rebuild comparisons therefore mix
  two effects: changed split-VTD weights and recovery of votes that the old
  representation could not allocate. They must not be described as a pure
  district-remapping delta unless compared on an identical matched-record
  universe.

## Published-lineage disposition

The 76 contest/year groups fall into two reviewed classes:

- 43 even-year groups have a legacy `coterminous_county_control` lineage and
  published congressional/House/Senate statewide totals that are internally
  inconsistent. The enforcement script now fails closed if that operation
  changes statewide party or total sums.
- 33 odd-year judicial groups use recovered official precinct returns. Their
  candidate totals conserve the retained official source; the published totals
  reflect legacy matching/coverage loss. Independent county controls support
  the recovered judicial totals, but adopting them remains a source-policy
  decision.

The largest candidate-versus-published changes are 2017 Superior Court
(+1,093,146 statewide), 2010 U.S. Senate (about -769,666), and 2010 governor
(about -767,320). These are source/coverage differences and cannot be caused
by district mapping, which conserves statewide totals.

## Source-policy follow-up

1. Retain `data/district_bef_candidate` as the reproducible staging snapshot.
2. Record the official judicial recovery and current precinct-source policy in
   permanent project documentation.
3. Do not reintroduce the legacy coterminous controls unless they can preserve
   party components, statewide totals, and equality across all three scopes.
4. Rerun the fail-closed acceptance and conservation checks after future source
   updates.

Before promotion, only `congressional_president_2024.json` was identical in all
party components and total votes to its legacy published counterpart.

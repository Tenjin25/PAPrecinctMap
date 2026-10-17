# Follow-up: original blocks and full-data acceptance

Current release: the narrow 2016 Emmaus correction is applied to five House
layers (ten district rows). See [RELEASE.md](RELEASE.md). The broader
comparisons below are retained pre-release diagnostic snapshots, not additional
approved changes. All other production vote values remain unchanged.

## Full acceptance rebuild and reuse: completed

`acceptance_integration.json` records the completed fresh build at source
implementation commit `26d3baa`, with 602 source content fingerprints and
268 output JSON fingerprints. It compares every rebuilt vote value and
candidate name with the original cold baseline: zero arithmetic/name changes.
The 54 retention county-metadata defects are repaired; 228 statewide-contest
files independently pass county/district-party arithmetic checks.

Thirty-three legacy judicial slices still lack allocation and county evidence.
These are missing-evidence failures, **not** 33 demonstrated vote-sum errors.
No actual county-arithmetic mismatches remain among evidence-bearing files.
The gate correctly stays BLOCKED: 5,409 published district differences, zero
statewide-party differences, zero unmatched/unallocated rows, zero coverage
changes, zero candidate-name changes, and six official Luzerne bound failures.
Missing evidence must not be synthesized from copied publication files.

Warm `--reuse` and unchanged `--incremental` both complete in about six seconds,
preserve every candidate JSON hash and the exact difference ledger, and rerun
the same blocking checks. The real-builder controlled-source lifecycle test
also verifies changed-year-only rebuilds, untouched-year byte identity,
two-year manifest retention, and rejection of changed vote results.

## Difference causes: further evidence

`verified_calibration_causes.csv` enumerates all 5,409 differences and verifies
258 complete before/after calibration explanations: 2018 Senate Congress 15,
House 196, Senate 47. Eleven additional rows have a calibration stage but
unresolved additional differences. The remaining 5,140 have no exact stage
evidence in those calibration ledgers. County components are not fabricated
for district-level calibration operations. `verified_cause_groups.csv` groups
the status by year, contest, scope and cause, explicitly marking missing
county attribution rather than inventing it.

PA-10's entire generic-candidate/publication delta matches its recorded DRA
calibration. After the user supplied original 2018 block assignments, the
direct official-precinct replay gives Casey +0.632418%, not the generic
candidate's +0.465088%. Both Census VAP and VAP_MOD give the same direct result.
The VTD bridge and precinct/city/township identities explain the geographic
discrepancy. See `../pa10_original_blocks/EVIDENCE.md`. Applying pre-calibration
geographic shifts directly to already calibrated publication values would
double-adjust the result and does not establish a valid replacement.

## Wider current-district coverage

`../original_block_years/README.md` covers every current congressional, House,
and Senate district for all contests present in the supplied 2016/2018/2020
archives: 2,970 distinct year/contest/scope/district rows, three models each.
All supplied block IDs match and all RDH source county-party quantities
conserve, but certified source-control differences remain explicitly listed.
House 134, House 95, House 191 and Senate 1 are high-priority next raw-source
reconciliations; their modeled differences are not proposed production edits.

Complete all-year, county-level causal attribution remains unfinished. The
new direct-block comparisons expand the evidence; they do not certify all
model outputs as official election-district results.

## Official raw-source follow-up on the priority districts

`../priority_counties_raw_years/README.md` extends the original-vote join to
six counties in all three supplied years. Of 55 targeted year/contest/district
rows, 24 have no unmatched rows in their owning counties and exact certified
county-party source controls. These include the 2016 Senate HD-134 and 2018
Governor HD-95 discrepancies; the compact table supplies exact candidate vote
counts, not only margins. Explicit House/congressional fragment IDs are kept
separate and tested against accidental normalization collisions.

All 2016/2018 raw-source controls in these counties match. Fifty-seven 2020
source-control cells differ and remain blocked rather than silently scaled.
Other unresolved source rows are separately retained, including the Chadds
Ford label discrepancy and historical localized Susquehanna/Philadelphia
rows. Even zero-vote unmatched rows remain visible. See the source-completeness
status before reading any subtotal as a complete district result.

## Lehigh 2016 paired-transfer follow-up

`../lehigh_2016/README.md` now traces all five 2016 contests across the county's
current House districts. All published district-party values are reproduced
by the baseline, and all three diagnostic paths conserve official county-party
totals. HD-134's Senate gain of 1,306 Democratic, 1,562 Republican and 127 other
votes is paired with changes in HD-22, HD-131, HD-132 and HD-187.

Most of that effect is upstream source normalization/bridge composition:
1,305 / 1,567 / 127. Switching the original official rows from the historical
VTD bridge to original precinct blocks adds only 1 / -5 / 0 beyond that.
The normalized-source construction still needs its own row-level replay;
these stage deltas do not yet identify every underlying source transformation.
Twelve unmatched zero-vote intermediate rows remain explicitly recorded.
No production change is approved by this diagnostic.

The follow-up normalization replay now reproduces all stored Lehigh vote/geography
rows and baseline county/district/party values. It identifies reverse many-to-many
crosswalk contamination: current precinct keys are reversed into full source-VTD
unions, losing the fractional forward contributions. Emmaus 3 alone explains
a 306 Democratic / 376 Republican / 42 other transfer from HD-134 to HD-131.
See the retained reverse-crosswalk evidence and original-precinct effect ledger.
Candidate spelling differences are reported separately and remain unchanged.

## Wider exposure and conserved preview

`../reverse_crosswalk_exposure/README.md` inventories 121 cross-boundary
precinct/scope keys in 23 counties (14 congressional, 81 House, 26 Senate).
All-year grouped exposed source quantities are not adjudicated vote differences.
`../hybrid_review/README.md` lists all 143 changed district rows from 69
source-complete, conserved county slices in 19 baseline-reproducing layers.
They remain diagnostic, pending geographic review; calibrated layers are blocked.

An independent official-description benchmark in `../hd134_legal_membership/`
now checks all 11 contests in the three supplied years. For 2016 Senate it
gives HD-134 13,548 / 8,872 / 974, versus original-block 13,544 / 8,865 / 974.
The 11-vote difference is Salisbury ward 4 division 1, wholly included by the
official current description. Historical administrative-boundary continuity
still needs verification. This shows why even conserved original-block rows
must not be promoted indiscriminately.

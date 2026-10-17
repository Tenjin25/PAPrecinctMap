# Lehigh 2016: paired current-House diagnostic

Reproduce with `python data/district_reconciliation_work/reconcile_lehigh_2016.py`
after generating the priority-county original-source ledger. Production is untouched.

All five 2016 candidate House layers reproduce every published district-party
value. Their independent Lehigh county ledgers can therefore be compared with
the original official source without assuming a published county breakdown.
All three paths conserve the same official Lehigh party totals in all five
contests. Twelve zero-vote raw rows remain unmatched in the intermediate bridge
replay; they are retained explicitly and the zero-unmatched promotion gate is
not waived.

For U.S. Senate, original-precinct-block votes minus published votes are:

| Current House district | Democratic | Republican | Other |
| --- | ---: | ---: | ---: |
| 22 | -18 | -145 | -7 |
| 131 | -1,714 | -2,275 | -156 |
| 132 | +9 | +100 | +10 |
| 133 | 0 | 0 | 0 |
| 134 | +1,306 | +1,562 | +127 |
| 183 | 0 | 0 | 0 |
| 187 | +417 | +758 | +26 |
| County sum | 0 | 0 | 0 |

HD-134 moves from 12,238 / 7,303 / 847 to 13,544 / 8,865 / 974.
The intermediate replay uses the original official 2016 historical VTD code
(raw field 28), the maintained VTD bridge, and the current Carter/BEF Census
VAP weights. It produces 13,543 / 8,870 / 974. Thus the large discrepancy is
upstream source-path composition, not the final original-precinct versus
VTD-block geography choice. This is stage attribution, not yet a complete
precinct-level explanation of the normalized-source transformation.

Only four precinct identities change between that intermediate bridge and
original precinct blocks in the Senate replay: Allentown 15-4, Allentown 19-6,
Salisbury 4-1, and Washington Southern. HD-134's final geographic adjustment
is +1 Democratic, -5 Republican, 0 other. These are paired within Lehigh.

`source_precinct_path_comparison.csv` retains each named candidate, official
line, original RDH precinct identity, VTD targets, both district VAP weight
sets, allocations, and signed geographic effects. `county_district_path_comparison.csv`
separates normalized-source-to-raw-bridge effects from raw-bridge-to-original-block
effects. Neither stage is an observed block vote tally.

Next required evidence: replay the normalized-source construction itself with
its retained original precinct identities, resolve the zero-vote unmatched
rows, and independently verify the affected original RDH precinct footprints.
Do not promote the diagnostic totals or distribute residual votes.

## Normalization replay: reverse many-to-many crosswalk

The new `replay_lehigh_normalization.py` reproduces the stored normalized
vote/geography row multiset and every baseline county/district/party allocation
for all five contests, retaining original precinct identities. Candidate spelling
differences remain separately listed; no production candidate name is changed.

The major mechanism is now traceable: `match_row_to_current_vtds` reverses
the many-to-many `pa_vtd20_to_current_precinct.csv` into a set of source VTDs.
The allocator then uses full VAP for every recovered VTD, not the forward
crosswalk's fractional contribution. A forward areal/population interpolation
is not an invertible identity mapping.

Example: Emmaus District 3 -> `LEHIGH - 077780`. That current key receives
VTD `000780` with forward share 1 and VTD `001260` with share 0.028735632184.
The reverse lookup returns both full VTDs. For 2016 Senate this removes
306 Democratic, 376 Republican and 42 other votes from HD-134 and adds them
to HD-131, relative to original precinct blocks. Emmaus 5 and 6 similarly
account for 217/245/20 and 330/394/30 transfers. Other affected precincts are
fully listed in `normalization_precinct_district_effects.csv`.

`reverse_crosswalk_evidence.csv` retains each original label, normalized key,
recovered source VTD, forward share, and full-share reverse behavior. It can
be regenerated with `trace_lehigh_reverse_crosswalk.py`. Do not "fix" this
by renormalizing the inverse shares: preserve original source geography or
use an independently justified joint allocation instead. Official precinct
footprint checks and the zero-unmatched gate remain required before promotion.

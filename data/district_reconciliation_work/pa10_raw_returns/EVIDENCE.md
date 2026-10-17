# PA-10 2018: original precinct and calibration reconciliation

## Sources and independent controls

Pennsylvania's historical-data page links to the original 2018 general-election
precinct returns:
https://www.pa.gov/agencies/dos/resources/voting-and-elections-resources/voting-and-election-statistics/election-data

Direct download:
https://www.pa.gov/content/dam/copapwp-pagov/en/dos/resources/voting-and-elections/bulk-data/ElectionReturns_2018_General_PrecinctReturns.txt

A fresh download on 2026-10-16 is byte-identical to the retained source:
SHA-256 `3bee609f52349b979245634147ddab7f018a0115cce46b71da08fb6c415199bb`.
That is the original download's CRLF-byte checksum. The LF-normalized checksum
used by the cross-platform regression is
`a05eaf5062c9caa6e2c2142b228d6cf5eb45c17386be5efd32cf1b9ad3c7cfc6`.
The diagnostic handles both `41` and `041` county FIPS spellings. Omitting
the unpadded spelling would incorrectly drop 40 candidate rows in Cumberland.

All 1,756 named-candidate rows in 439 precincts match the maintained bridge;
zero unmatched rows or votes. Every row's integer district allocations sum
exactly to its original vote count. Original county totals match all three
retained certified county-party controls exactly:

| County | Democratic | Republican | Other |
|---|---:|---:|---:|
| Cumberland | 47,738 | 54,525 | 2,137 |
| Dauphin | 59,533 | 47,152 | 2,023 |
| York | 69,272 | 95,814 | 3,726 |

## What the current-plan geographic source establishes

The state's current 2022-plan description is at:
https://www.pa.gov/agencies/vote/resources/redistricting/pennsylvania-redistricting-us-congress

Dauphin is wholly PA-10. Within the other two counties, North Newton and
Jackson Precinct 1 contain the described partial-precinct boundaries. Jackson
Precinct 2 is wholly PA-10 in that description. This does **not** establish that
a precinct labeled Jackson P 2 in 2018 had exactly the same boundary. The
2018 bridge sends a small part of that old precinct into current VTD 000420;
that is a vintage/bridge uncertainty to investigate, not permission to override
the old precinct to PA-10 by name alone.

`Scripts/build_pa_modern_precinct_crosswalk.py` constructs the retained
`rdh_precinct_blocks` bridge weights using **VAP_MOD**, not unmodified Census
block VAP. Applying Census VAP in the final BEF join does not remove this
earlier modeled weighting. Original 2018 RDH block assignments/populations or
adequate election-era precinct geography are needed to replace that step.

RDH's public block metadata confirms how VAP_MOD and precinct assignments
were constructed:
https://redistrictingdatahub.org/wp-content/uploads/2022/11/readme_pa_2018_gen_2020_blocks.txt
The retained metadata SHA-256 is
`84fd57bc89be16ff323b3e0aad39c9d76e462be2550e7c8ba0af31672460aa29`.
The dataset lists a 162.9 MB SHP archive, but its download redirects to login:
https://redistrictingdatahub.org/dataset/pennsylvania-2018-general-election-results-disaggregated-to-the-2020-block/
Do not bypass that requirement or mistake the login HTML for the ZIP.

## Quantified stages

| Current PA-10 variant | Democratic | Republican | Other | Total | Casey margin |
|---|---:|---:|---:|---:|---:|
| Published | 144,963 | 143,119 | 5,933 | 294,015 | +0.627179% |
| Generic normalized-source Carter/VAP candidate | 144,682 | 143,315 | 5,926 | 293,923 | +0.465088% |
| Original precinct rows through maintained bridge and Carter/VAP | 144,688 | 143,322 | 5,926 | 293,936 | +0.464727% |

The last row is a diagnostic model, **not** an official observed district
tally. The raw-versus-normalized difference is exactly localized in
`county_source_path_comparison.csv`: Cumberland Other -2; York Democratic +6,
Republican +7, Other +2; Dauphin unchanged. No residual is spread among counties.

The existing, retained before/after calibration ledger
`data/district_bef_audit/dra_2018_us_senate_congressional_changes.csv` exactly
matches the generic candidate before calibration and publication after it.
Thus the entire candidate-versus-published PA-10 delta (-281 D, +196 R, -7 O,
-92 total) is explained by that documented DRA calibration operation. This
explains provenance; it does not independently validate the calibrated result.
The DRA share file has 17 district rows but lacks an independently verified
export/map identifier. Do not manufacture county components for that operation.

The Wikipedia election article inspected on 2026-10-16 lists 18 districts and
rounded PA-10 percentages of 50% Casey and 48% Barletta. It is not a current-plan
Casey +0.6% benchmark. The original returns grouped by their election-era
congressional field give Casey +1.586384% in old PA-10; these IDs must never be
substituted for current Carter assignments.

## Decision

No production change proposed. The original-source replay is consistent with
the generic candidate's approximately +0.465% margin, but still relies on a
legacy VAP_MOD bridge and unresolved precinct vintage. Neither geographic
exactness nor independent official support for the DRA-calibrated district
margin has been established. Retain published values pending that evidence.

Reproduce with `python data/district_reconciliation_work/reconcile_pa10_raw_returns.py`.
Verify with `python data/district_reconciliation_work/test_reconciliation_diagnostics.py`.

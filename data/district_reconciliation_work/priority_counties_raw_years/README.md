# Official raw-return follow-up: six priority counties, 2016/2018/2020

Counties: Cumberland, Dauphin, York, Lehigh, Delaware and Philadelphia. Original
official statewide-contest candidate rows are joined to the supplied original
RDH election-precinct block assignments, then to current congressional, House
and Senate BEFs using Census block VAP. No production output is modified.

Matching retains official municipality type, zero-padded ward/division numbers,
and **explicit congressional/House fragments**. Springfield 3-2 (HD161) and
(HD165), and York Township 5-3 (CD10) and (CD11), are distinct source identities.
They are not merged by stripping parentheses. A pooled original source is
used only when a distinct fragment is absent and its current per-scope block
assignment is wholly in one district. Whole counties are assigned intact
using the 99.9% Census-VAP criterion, even when a precinct label is unresolved.
The 2016 export's separate ward/precinct fields are assembled explicitly;
the 2018/2020 exports already put the complete label in their name field.

`priority_district_source_completeness.csv` evaluates 55 year/contest/district
rows for PA-10, HD-134, HD-95, HD-191 and SD-1. Twenty-four have complete source
matches in every owning county and matching certified county-party controls:
15 in 2016, six in 2018, three in 2020. This establishes source completeness,
not a claim that RDH geographic assignments are observed ballot fragments.

Examples of complete-source diagnostic results:

| Year / contest / district | Direct D | Direct R | Direct Other | Published D | Published R | Published Other |
|---|---:|---:|---:|---:|---:|---:|
| 2016 Senate / HD-134 | 13,544 | 8,865 | 974 | 12,238 | 7,303 | 847 |
| 2018 Governor / HD-95 | 11,262 | 4,609 | 297 | 11,857 | 5,494 | 323 |
| 2018 Senate / PA-10 | 144,159 | 142,310 | 5,901 | 144,963 | 143,119 | 5,933 |

These are review candidates, **not promoted district edits**. A complete
conserved county/district transfer proposal must precede production changes.
Applying an old pre-calibration geographic delta to already calibrated
publication values can double-adjust the result.

`official_source_vs_certified_county_controls.csv` compares all 198 source
county/contest/party cells. All 2016 and 2018 cells match. Fifty-seven 2020
cells do not; their exact signed differences remain visible and are not
silently corrected, distributed statewide, or called rounding. A slice with
any source-control mismatch remains ineligible for promotion even if its
precinct names all match (for example, 2020 Auditor / HD-95).

Unresolved rows are retained per scope in each `*_unmatched.csv`, including
zero-vote source rows. Among them are the Chadds Ford Southeast/Southwest
label discrepancy and election-era localized Susquehanna/Philadelphia rows.
The township's official page names Northeast and Southwest districts:
https://www.chaddsfordpa.gov/elected-township-officials
That alone does not authorize guessing a historical geographic join. No
nearest-name or benchmark-margin-fitting fallback is used.

Each `*_rdh_precinct_district_vap.csv` retains the original source identities
and current district weights. `*_county_district_votes.csv` retains allocated
integer official-source votes. The larger per-source-candidate allocation
ledgers remain local and are reproducible from the original archives; they
are not required to read the compact source-completeness fixtures.

Reproduce:

```
python data/district_reconciliation_work/audit_priority_counties_raw_years.py
python data/district_reconciliation_work/summarize_priority_counties_raw_years.py
```

Individual years can be rebuilt by adding `2016`, `2018`, or `2020` to the
first command. Unmatched-scope vote sums count a source row separately in
each affected scope; they are not unique statewide ballot counts.

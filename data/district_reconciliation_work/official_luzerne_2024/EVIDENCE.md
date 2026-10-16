# Official Luzerne 2024 benchmark evidence

Source: the 2024 general-election link in the county's official archive:
https://www.luzernecounty.org/404/Election-Results-Archive

It links to https://results.enr.clarityelections.com/PA/Luzerne/122840/ .
The public app's `current_ver.txt` returned version `355923`; its config
identified English (`en`). Retained public responses are:

- `355923/json/config.json`
- `355923/json/en/summary.json`
- `355923/json/details.json`
- `355923/json/sum.json`
- `355923/json/en/electionsettings.json`
- `355923/json/vt.json`

The settings report last updated 12/3/2024 9:52:40 AM EST. The generic page
header says Unofficial Results, so the retained certified county controls
remain the independent control; do not infer certification from the URL.

Named Senate candidates in summary contest K=2 total Casey 64,546;
McCormick 87,096; Thomas 1,813; Hazou 1,142; Selker 493. These agree exactly
with retained county controls (Other 3,448; total 155,090). The API also
repeats the 75 write-ins as both a Write-in aggregate and SCATTER child.
Do not sum aggregate and child columns together or silently add write-ins
to the established named-candidate universe.

## Butler Township District 5

Details K=2 reports one Senate row, with votes in candidate order:
`[289,856,9,3,5,1,1]`. The final two entries are the repeated write-in
aggregate/child, not two separate ballots.

Congressional contest K=6 (CD-8) reports this precinct with Cartwright 82,
Bresnahan 198. Contest K=7 (CD-9) reports the same precinct with Waldman
192, Meuser 675, plus one write-in represented twice.

Thus the county's election precinct genuinely spans both current CDs.
Its Senate votes are pooled across that boundary. The retained RDH matrix
puts all five named Senate totals on `BUTLER D 5 (USC 8)` and zero on
`BUTLER D 5 (USC 9)`. These are not independently observed Senate totals
for the two congressional fragments. Using the suffix as an exact Senate
assignment would move pooled votes based on a storage convention.

The published county-clustered path models the pooled Senate row using
Carter VTD `(079,000152)`, whose BEF block VAP is CD-8=403 and CD-9=987.
Its CD-8 fraction is 403/1390. That produces Casey 83.7892086331 and
McCormick 248.1784172662 before final rounding. This remains a population
model, not an exact recovered ballot split. Congressional-race vote shares
would be a different model and would not establish Senate party splits.

## Mail, provisional, and election-day evidence

The county vote-type response identifies Election Day, Provisional, and
Mail in / Absentee. For Casey these are `[37678,961,25907]`; for McCormick
`[70862,1037,15197]`. This establishes county ballot-category totals, but
the retained `details.json` supplies combined precinct totals. Do not
invent congressional-fragment or precinct mail rows from the county sums.

## Recommendation

Retain this pooled precinct's geographically modeled allocation pending
fragment-specific Senate evidence. The independent county returns support
pooling, not an override assigning every Senate vote to CD-8. This does not
prove every other published Luzerne allocation correct; review those paths
individually using the VTD reconciliation ledger.

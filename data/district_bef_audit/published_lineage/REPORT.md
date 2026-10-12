# Published lineage reconciliation

The BEF candidate conserves every selected source record, has no unmatched records, and passes the block/district checks. It is not promotion-ready because its selected source lineage does not reproduce the currently published totals.

- Contest/year groups audited: 76
- Published files with changed totals: 227
- Groups where published congressional/House/Senate totals disagree internally: 43
- Individually total-equivalent files: 1

## Classification counts

- `coterminous_house_control`: 43
- `official_judicial_precinct_recovery`: 33

## Year summary

| Year | Groups | Internally inconsistent | Largest absolute delta |
|---:|---:|---:|---:|
| 2000 | 5 | 5 | 14,381 |
| 2001 | 1 | 0 | 205,224 |
| 2002 | 1 | 1 | 89,974 |
| 2003 | 1 | 0 | 206,698 |
| 2004 | 5 | 5 | 11,325 |
| 2006 | 2 | 2 | 6,959 |
| 2007 | 2 | 0 | 369,382 |
| 2008 | 4 | 4 | 8,720 |
| 2010 | 2 | 2 | 769,666 |
| 2012 | 5 | 5 | 32,366 |
| 2014 | 1 | 1 | 492,524 |
| 2015 | 1 | 0 | 269,265 |
| 2016 | 5 | 5 | 12,233 |
| 2017 | 6 | 0 | 1,093,146 |
| 2018 | 2 | 2 | 32,095 |
| 2019 | 4 | 0 | 83,423 |
| 2020 | 4 | 4 | 12,269 |
| 2021 | 6 | 0 | 113,267 |
| 2022 | 2 | 2 | 3,266 |
| 2023 | 5 | 0 | 241,975 |
| 2024 | 5 | 5 | 3,210 |
| 2025 | 7 | 0 | 152,877 |

## Largest internal published inconsistencies

| Year | Contest | CD total | House total | Senate total | Spread |
|---:|---|---:|---:|---:|---:|
| 2018 | governor | 5,013,259 | 5,035,877 | 5,013,253 | 22,624 |
| 2018 | us_senate | 5,010,035 | 5,032,641 | 5,010,028 | 22,613 |
| 2010 | governor | 4,753,730 | 4,744,830 | 4,753,731 | 8,901 |
| 2010 | us_senate | 4,745,534 | 4,736,707 | 4,745,537 | 8,830 |
| 2014 | governor | 3,982,643 | 3,975,471 | 3,982,646 | 7,175 |
| 2020 | attorney_general | 6,789,699 | 6,790,399 | 6,789,701 | 700 |
| 2020 | treasurer | 6,743,376 | 6,744,071 | 6,743,377 | 695 |
| 2020 | auditor | 6,733,197 | 6,733,882 | 6,733,194 | 688 |
| 2012 | president | 5,734,022 | 5,733,358 | 5,734,022 | 664 |
| 2006 | us_senate | 4,078,948 | 4,078,346 | 4,078,948 | 602 |

## Exact-equivalence allowlist

Only files with identical Democratic, Republican, other, and total vote sums are eligible for independent promotion. The current allowlist is:

- `congressional_president_2024.json`

## Release conclusion

Do not bulk-promote the candidate. Internal published scope disagreement proves that some existing files are defective, while large consistent differences—especially multi-seat judicial contests—require recovery of the published candidate-selection and supplemental-source rules. Mapping corrections should be promoted only after a source-equivalent rebuild or explicit contest-by-contest replacement approval.

See `contest_year_classification.csv`, `published_scope_inconsistencies.csv`, and `promotion_manifest.json` in this directory.

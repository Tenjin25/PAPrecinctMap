# Judicial source-lineage reconciliation

All 33 odd-year judicial groups use retained official Pennsylvania precinct-return files in the BEF candidate. Every source row is matched and conserved. The older published district files were built with the legacy OpenElections precinct matcher and are uniformly below the independent county aggregates.

- Groups: 33
- Candidate unmatched rows: 0
- Maximum official-precinct versus county-control difference: 0.288%
- Published shortfall range versus county controls: 3.959% to 14.855%
- Conclusion: the large candidate/published differences are recovered precinct coverage, not BEF mapping or a multi-seat candidate-set error.

Small official-versus-county-control residuals remain (at most 0.289%). Deep comparison localized 2,016 nonzero county/contest cells, and every difference is positive. The normalized historical CSVs contain fractional disaggregated rows; the old county builder truncated each row before summing. The builder now preserves fractions and rounds once per county/contest using largest remainder.

## Largest recovered totals

| Year | Contest | Published | Official precinct source | Recovered | County control |
|---:|---|---:|---:|---:|---:|
| 2017 | superior_court | 6,560,430 | 7,653,576 | 1,093,146 | 7,636,096 |
| 2017 | commonwealth_court | 3,303,365 | 3,852,260 | 548,895 | 3,844,402 |
| 2007 | superior_court | 5,211,701 | 5,581,083 | 369,382 | 5,567,692 |
| 2017 | supreme_court | 1,790,575 | 2,086,025 | 295,450 | 2,082,048 |
| 2015 | supreme_court | 5,614,492 | 5,883,757 | 269,265 | 5,866,856 |
| 2007 | supreme_court | 3,780,250 | 4,045,947 | 265,697 | 4,036,897 |
| 2023 | superior_court | 5,366,970 | 5,608,945 | 241,975 | 5,604,300 |
| 2017 | supreme_court_retention_debra_todd | 1,345,727 | 1,582,758 | 237,031 | 1,578,858 |
| 2017 | supreme_court_retention_thomas_g_saylor | 1,338,265 | 1,575,067 | 236,802 | 1,571,142 |
| 2017 | superior_court_retention_jacqueline_o_shogan | 1,315,722 | 1,549,203 | 233,481 | 1,545,269 |
| 2003 | supreme_court | 2,241,671 | 2,448,369 | 206,698 | 2,444,332 |
| 2001 | supreme_court | 1,181,096 | 1,386,320 | 205,224 | 1,383,947 |

## Promotion rule

Do not preserve the lower published totals merely for backward compatibility. Regenerate all three scopes together from the same official precinct source, then either retain exact official precinct totals or apply one documented statewide/county control consistently across every scope.

## County-level residual localization

The deep reparse found 2,016 nonzero county/contest revisions. All are positive. They are listed in `judicial_county_source_revisions.csv`; they are differences between the retained official precinct exports and the older row-truncated county-control JSONs, not allocation loss.

## County-level residual localization

The deep reparse found 2,016 nonzero county/contest revisions. These are listed in `judicial_county_source_revisions.csv`; they are differences between the currently retained official precinct exports and the older generated county-control JSONs, not allocation loss.

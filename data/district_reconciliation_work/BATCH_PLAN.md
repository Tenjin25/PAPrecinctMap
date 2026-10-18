# Current-decade district reconciliation batch plan

Baseline: `origin/main` at `6b293db`. The historical decision ledger contains
5,409 differing district rows: 258 exactly explained by retained DRA stages,
11 more by DRA plus Westmoreland's localized 2018 certification-allocation
ordering, and 5,140 without an exact retained-stage explanation. The current
all-ledger replay adds 12 exact county-clustered stage paths, 1,488 exact
county-conserved RDH stage paths, and all 270 rows of the retained VEST 2020
President publication pipeline. The exact Carter-adjusted historical judicial
replay adds 3,308 rows. The retained modern publication-history chain closes
the final 62 rows, for all 5,409 explained and zero without exact numerical
lineage. The original 269 count remains recorded as a historical checkpoint.

| Rank | Batch | Affected rows / coverage | Source completeness | Expected impact | Promotion gates |
|---:|---|---|---|---|---|
| 1 | Actual reverse-crosswalk fallback | 121 potentially exposed precinct/scope keys were known; the first executed 2016 replay finds 32,989 actual share-sensitive fallback source rows, 3,170 of which change at least one scope allocation | Complete normalized 2016 source, certified county controls, Carter bridge, VAP and all three BEFs | Isolated paired transfers in 505 generic-candidate district rows; no production edits proposed | Actual-path precedence, unique weighted VTD targets, exact source-row and county-party conservation, VAP 99.9% rule, largest remainder, Emmaus no-double-adjustment, benchmark preservation |
| 2 | All-stage lineage replay | All 5,409 baseline rows now have exact directed numerical lineage; the final 62 use the retained 2022/2024 publication-history chain | Mixed by year; retained official-return, NHGIS, county-control, DRA, RDH, Carter block-equivalency, VAP_MOD, localized-residual and integerization artifacts only | Close numerical lineage without treating it as geographic validation | Exact stage equality, source fingerprints, zero unmatched/unallocated rows where source replay is asserted, explicit controls, no residual inference |
| 3 | Original 2016–2020 archive slices | 24 of 55 priority rows are source-complete; 69 county slices already conserve in the diagnostic hybrid | Complete only for explicitly marked county/contest slices | Independent geography decisions for selected uncalibrated slices | Direct precinct identity, exact certified county controls, zero unmatched rows, whole-county integrity, paired transfers |
| 4 | Legacy judicial official-source replacement evidence | Historical publication lineage is exact for all 3,308 judicial difference rows; independently rebuilt county/allocation evidence is recovered for 27 of 33 acceptance files and six remain blocked | Retained official files support 27; the 2019 Commonwealth and 2025 Supreme contest rows are absent | Keep numerical lineage separate from whether a modern official-source replacement is better supported | Retained-source-only county records, allocation provenance, fingerprints, no publication-derived evidence |

Production is retained unless a row is independently validated and individually
approved. Pre-calibration deltas are never layered onto calibrated publication.

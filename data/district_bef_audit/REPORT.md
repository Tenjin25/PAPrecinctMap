# Pennsylvania Carter BAF / 2022-line BEF audit

Audit date: 2026-10-08. Published files in `data/district_contests` were read only.

## Recommendation

Do not replace the published district JSONs yet. The BEFs are internally clean and are preferable to the prior spatial-overlay district crosswalks, but a full rebuild differs materially from published files because the current working pipeline uses different historical matching, supplemental sources, and calibrations. Those source-lineage differences dominate the small mapping-only changes.

The exact BEF allocation should be adopted after the 53 real blocks represented as 107 A/B overlay fragments in the previous district crosswalks are documented and the historical source/coverage changes are reviewed contest by contest.

## BAF provenance and vintage

- The Carter-adjusted source actually consumed by the district allocator is `data/crosswalks/pa_block20_to_vtd20.csv` (SHA-256 `5999f2eb0fdaac5e92a61949f25db312bdd77a4bbf2f6199a1360fbaecbfd031`). It contains 336,985 unique 15-digit 2020 census block GEOIDs.
- It first entered repository history in commit `25b3846336371e27ebdb90a51792c9dc6d2958c5` on 2026-09-08 (`Correct 2012 district reaggregation`). That is the repository vintage of the maintained artifact.
- Its block universe is identical to `BlockAssign_ST42_PA.zip::BlockAssign_ST42_PA_VTD.txt`, whose ZIP member timestamp is 2020-12-11 15:39:36. It is not byte-for-byte or assignment-identical: 17 blocks have changed VTD/county assignments.
- Three of the 17 changes intentionally cross the county encoded in the block GEOID (two Centre blocks assigned to Clearfield VTDs and one Clearfield block assigned to a Centre VTD). These are Carter-adjusted assignments, not malformed GEOIDs.
- The repository does not retain a source URL, source archive name, acquisition date, or generator for the Carter-adjusted CSV. Therefore its upstream publication vintage cannot be proven from this workspace. The defensible statement is: 2020 block universe and base BAF, 17 locally retained Carter adjustments, artifact committed 2026-09-08. The README should not claim a more specific external vintage until that provenance is added.
- The `CD`, `SLDL`, and `SLDU` members inside `BlockAssign_ST42_PA.zip` are December 2020 products and were not used as evidence for the 2022 lines.

The exact 17 changes are in `carter_vs_zip_vtd_changes.csv`.

## BEF integrity and joins

All joins used the 15-character block GEOID as text; leading zeros were preserved.

| Scope | BEF rows | Duplicates | Missing vs Carter BAF | Extra vs Carter BAF | Invalid districts | Split VTDs |
|---|---:|---:|---:|---:|---:|---:|
| Congressional | 336,985 | 0 | 0 | 0 | 0 | 14 |
| State House | 336,985 | 0 | 0 | 0 | 0 | 8 |
| State Senate | 336,985 | 0 | 0 | 0 | 0 | 4 |

The three reported county mismatches in each BEF join are the same Carter cross-county assignments described above, not BEF errors. District ranges are valid: CD 1-17, House 1-203, and Senate 1-50.

Split details and block counts are in `congressional_split_vtds.csv`, `state_house_split_vtds.csv`, and `state_senate_split_vtds.csv`.

## Relationship to the previous district mapping

For every common valid 15-digit block, the old overlay crosswalk and the new BEF district assignment agree. The difference is representation at split geometry:

- The prior `pa_block20_to_*_2022.csv` files contain 337,039 keys.
- They omit 53 real Carter/BEF block GEOIDs and instead contain 107 non-census A/B fragment IDs (for example `420912078002006A`).
- Those fragments cannot join to a 15-digit BAF record. The old allocator therefore normalized district weights using only the remaining real blocks in the affected VTDs.
- The BEFs restore all 53 real blocks and consequently adjust split-VTD proportions. This is the entire mapping-only effect; no common real block changes district.

Across the rebuild, the BEF changed 679 district rows in 87 contest files relative to the old uncalibrated mapping. Every contest retained exactly the same statewide total. The largest mapping-only district-total changes were:

| File / district | Vote change |
|---|---:|
| `state_senate_treasurer_2024.json`, SD 7 | +178 |
| `state_senate_us_senate_2024.json`, SD 7 | +175 |
| `state_senate_attorney_general_2024.json`, SD 7 | +173 |
| `state_house_attorney_general_2020.json`, HD 194 | +172 |
| `state_house_auditor_2020.json`, HD 194 | +172 |
| `state_house_attorney_general_2024.json`, HD 194 | +171 |
| `state_senate_auditor_2024.json`, SD 7 | +171 |

The offsetting losses are present in neighboring districts; statewide deltas are zero.

## Calibration and published-data comparison

Applying the existing DRA share calibration changes party composition in 1,258 district rows across 10 presidential files, but it does not change any district total or statewide total. This is distinct from the BEF mapping effect.

The BEF-calibrated rebuild differs from published data in 11,925 district rows across 211 files. In 131 files, statewide totals also differ. These cannot be caused by district mapping because district mapping conserves statewide totals. They reflect later/alternate source selection, historical precinct matching, exact benchmarks, supplemental returns, or other calibration already embedded in published JSONs.

The largest published-versus-rebuild gaps are historical source/coverage effects, including 2010 U.S. Senate (-935,723 statewide), 2010 governor (-934,456), and 2014 governor (-633,432). These are not evidence against the BEFs; they show that the isolated rebuild is not source-equivalent to the published production lineage.

Coverage does not improve or worsen between the old mapping and BEF mapping. Relative to published files, the rebuild adds several 2011 retention slices from current uncommitted supplemental sources, omits published-only 2019/2025 slices and the direct 2022 state-Senate slice, and improves 2001 Superior Court district-row coverage from 97 to 99 House districts and 30 to 31 Senate districts. Those are source changes, not BEF effects. See `coverage_changes.csv`.

## Conservation and unmatched records

- Block joins: no duplicate, missing, or extra records in any Carter-to-BEF join.
- Previous overlay: 53 unmatched real blocks and 107 unmatched A/B fragments per scope.
- Allocation: `allocate_votes_by_block_counts` uses largest remainder and conserves every matched precinct-candidate row. The rebuilt files pass `Scripts/audit_district_vote_conservation.py`.
- Contest/statewide: 96 contest-year groups were checked; party components equal total votes in every output, and congressional, House, and Senate statewide totals agree exactly for every group.
- Mapping comparison: all 87 affected contest files have statewide delta zero.
- Source matching: the production builder now emits source, matched, unmatched, allocated, and unallocated row/vote counts, the complete unmatched precinct-key list, and unmatched votes by precinct key in each file's `meta.allocation_audit`. Every row is now matched and every allocated contest conserves its source votes. Publication remains blocked only by explained and still-unreconciled differences between the chosen source returns and the currently published district totals.

## All-contest production candidate addendum

`Scripts/build_bef_candidate.py` copied the published directory to `data/district_bef_candidate`, rebuilt every published statewide-derived contest through the BEF production path, preserved direct district-race slices, and applied fail-closed acceptance checks. It did not modify `data/district_contests`.

The current candidate is **BLOCKED**:

- Carter/BEF block join complete: pass.
- Vote conservation for every matched precinct/candidate row: pass.
- Congressional, House, and Senate totals agree within each rebuilt contest/year: pass.
- Published file coverage unchanged: pass.
- No unmatched or unallocated source rows: pass (zero files).
- Published statewide totals unchanged: fail (227 files across the three scopes).

The NHGIS-derived historical crosswalk is active for all historical returns. It supplies the maintained `historical_vtd_block_chain` mappings in `pa_historical_precinct_to_vtd20.csv`; those mappings are composed from the local NHGIS 2000-to-2010 and 2010-to-2020 block relationships. Odd-year official judicial exports now retain their numeric and alphanumeric historical precinct codes and resolve through the adjacent even-year NHGIS chain. A maintained exact alias index is used only when its target also exists in the Carter BAF/BEF VTD universe. No unconstrained fuzzy matching is used.

The historical-code recovery eliminated the former 2001 Supreme Court gap completely and reduced the former 2003 Supreme Court gap from 75,359 votes to zero. Fifteen initial one-to-one legacy labels reduced the unique unresolved set from 47 to 32; direct use of the NHGIS 2010-to-2020 block chain reduced it to 16. A downloaded MGGG Pennsylvania archive corroborated the 2010 VTD codes but is a Census VTD layer, not the missing older county split-precinct geometry. Exact Philadelphia county/VTD concatenations, exact surviving Montgomery VTDs, and Delaware/Erie legacy labels whose every plausible VTD has the same CD118/SLDL22/SLDU22 signature then reduced the unresolved set to one.

The final label, `MONTGOMERY|HORSHAM DISTRICT 2 B`, is resolved through the OpenPrecincts PA18G lineage. Its documentation identifies Horsham 2-2 A/B as obsolete congressional fragments and explicitly recombines both to Horsham 2-2; the maintained alias/Carter target for that precinct is VTD20 `001085`. The final all-contest candidate therefore has **zero unmatched records, zero unallocated votes, and zero conservation failures**. The candidate is still marked `BLOCKED` because 227 candidate files have statewide totals different from the currently published files; those source-lineage discrepancies must be reviewed before adoption.

The large 2010 published comparison is now explained as a published-data defect rather than a BEF effect. The precinct source totals are 3,980,353 for U.S. Senate and 3,990,900 for governor, while the published district JSONs sum to 4,745,534 and 4,753,730. The candidate follows the source and leaves only 4,220 and 4,214 unmatched votes, respectively; it must not be inflated to reproduce the published totals.

Machine-readable gate results and the largest changes are in `data/district_bef_candidate/acceptance_report.json`; complete unmatched keys are embedded in the corresponding candidate JSON files under `meta.allocation_audit.unmatched_precincts`.

## Artifacts

- `audit_report.json`: machine-readable structural and comparison summary.
- `district_vote_changes.csv`: every changed district row for mapping, calibration, and published comparisons.
- `coverage_changes.csv`: added, omitted, and changed-coverage slices.
- `old_uncalibrated/`, `bef_uncalibrated/`, `bef_calibrated/`: isolated JSON builds; none replace published data.
- `Scripts/audit_carter_bef_aggregation.py`: reproducible audit driver.
- `Scripts/build_bef_candidate.py`: isolated all-contest rebuild and fail-closed release gate.
- `data/district_bef_candidate/acceptance_report.json`: current all-contest acceptance result.

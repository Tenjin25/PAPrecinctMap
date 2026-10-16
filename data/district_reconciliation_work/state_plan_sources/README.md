# Official Pennsylvania 2022 plan assignments

Downloaded 2026-10-16 from the final-plan links at https://redistricting.state.pa.us/maps/:

- Congressional: https://redistricting.state.pa.us/Resources/GISData/Districts/Congressional/2021/CSV/2022-02-25%20Carter-adjusted.csv
- House: https://redistricting.state.pa.us/Resources/GISData/Districts/Legislative/House/2021-Final/CSV/2022%20LRC-House-Final.csv
- Senate: https://redistricting.state.pa.us/Resources/GISData/Districts/Legislative/Senate/2021-Final/CSV/2022%20LRC%20Senate%20Final.csv

The congressional URL serves an XLSX workbook despite its CSV suffix. Original bytes are retained under `congressional.csv`; the comparison script detects the actual format.

Each state file contains 337,039 assignments; each Census BEF contains 336,985. All shared block IDs have identical district assignments. The state files replace 53 whole-block IDs with 107 suffixed fragment IDs. These fragments occur in the official state originals; their existence is not evidence of a local overlay defect.

Only parent block `421010257002008` has fragments assigned to different districts: House 194 (`B`) and House 200 (`A`). Congressional and Senate fragment siblings all share their parent's Census district. Before changing House allocation, obtain fragment geography and population evidence; a whole-block BEF cannot supply the fragment VAP. Do not assign half the population to each fragment merely because there are two fragments.

This verifies the current-plan assignment inputs. It does not validate historical election precinct-to-VTD lineage, resolve mail rows, or establish that either modeled district result is more accurate. Production outputs remain unchanged.

Reproduce with `python Scripts/audit_state_plan_assignments.py`. Checksums, all raw assignment differences, and grouped fragment assignments are emitted alongside this file.

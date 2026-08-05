# Keystone State Explorer (Formerly PAPrecinctMap)

Interactive Pennsylvania election map for data journalists, students, and political junkies.

This project combines a static web app (`index.html`) with a reproducible Python data pipeline that builds precinct, county, and district election layers for analysis and storytelling.

## Project Name Change

- Old project/repo name: `PAPrecinctMap`
- Current product name: `Keystone State Explorer`

If you publish as a GitHub Pages project site, your URL path usually includes the repo name, for example:

`https://<username>.github.io/PAPrecinctMap/`

The app is Pages-aware and auto-detects this project base path at runtime so data assets resolve correctly on the published site.

## Who This Is For

- Data journalists: quickly test county/district narratives, identify shifts, and pull map-ready context.
- Students and educators: explore election geography and compare statewide vs district outcomes.
- Political enthusiasts: inspect how margins move over time by county, precinct, and district.

## What You Can Do

- View Pennsylvania contests across years (manifest-driven from `data/contests/manifest.json`).
- Load historic presidential county results back to `2000`, with manifest-backed contest slices and CSV fallback support for older source exports.
- Switch map views:
  - Counties
  - Congress
  - State House
  - State Senate
- Switch visual modes:
  - Margins
  - Winners
  - Shift (change vs prior cycle when available)
  - Flips (bold colors for actual flips, lighter party tints for held areas, gray when no usable prior exists)
- Use fly-to search for counties, districts, and precinct tokens.
- Enable precinct overlay for fine-grained local patterns.
- View browser-ready precinct returns for presidential and statewide election years from `2000` through `2024`, with current-precinct geometry alignment.
- Aggregate the same precinct-return rows in county mode or inspect them at precinct level when the overlay is enabled.
- Pin hover cards and inspect trend history for selected geography.
- Use the compact hover tooltip system in `index.html`, with desktop previews and mobile-friendly expandable detail cards.
- Use the Pennsylvania-themed legend, selected-area panel, hover ribbons, and responsive mobile controls.

## Local Preview Notes

- `index.html` now stamps a build id onto both the page URL and data requests to shake loose stale browser cache when testing local updates.
- Precinct-return data is indexed by `data/precinct_returns_manifest.json`; rebuilds should refresh the manifest and the browser cache-buster together.
- If you are comparing behavior against the older backup file `index .v1.html`, remember it is a separate snapshot and will not automatically pick up fixes made in `index.html`.

## Audience Workflows

### For Data Journalists

1. Pick contest + year, start in county view for statewide context.
2. Switch to Shift mode to spot movement against the prior cycle.
3. Jump to specific counties/districts with fly-to search.
4. Pin areas and compare trend history before writing claims.
5. Cross-check edge cases with source files in `data/Openelections/`.

### For Students and Instructors

1. Use county view to explain statewide margins and turnout structure.
2. Switch to district views to discuss boundary effects and representation.
3. Compare Margins vs Winners vs Shift to distinguish "who won" from "how much changed."
4. Use repeated workflows across years to build reproducible classroom exercises.

### For Political Junkies

1. Start with your office of interest (President, Governor, Senate, etc.).
2. Use fly-to search to jump to your county, district, or precinct.
3. Toggle precinct overlay at higher zoom for neighborhood-level texture.
4. Track trend history on pinned geographies to see whether movement is persistent or cyclical.

## Coverage Snapshot

Based on the current manifests in this repository:

- Statewide contest years: `2000` to `2024`
- District-scope years: `2000` to `2024`
- Statewide contest types currently present:
  - `president`
  - `governor`
  - `us_senate`
  - `attorney_general`
  - `treasurer`
  - `auditor`

Election-cycle rules reflected in the manifests and build pipeline:

- Governor: midterm years only (`2002`, `2006`, `2010`, `2014`, `2018`, `2022`).
- Attorney General, Auditor General, and State Treasurer: presidential years only (`2000`, `2004`, `2008`, `2012`, `2016`, `2020`, `2024`).
- Secretary of the Commonwealth: omitted because it is appointed, not elected.
- Pennsylvania had no U.S. Senate general election in `2008`.
- Actual district race slices currently present:
  - `us_house`: `2022`, `2024`
  - `state_house`: `2022`, `2024`
  - `state_senate`: `2022`, `2024`

Note: district views can include both actual district races and statewide contests reallocated to current district lines, depending on contest type/year coverage.

## Which File Is "The App"?

- Primary app entry: `index.html`
- Supporting pipeline script: `build_pa_data_layers.py`
- `index.html` is the primary PA production entrypoint.

## Access

- This project is intended to be consumed through your GitHub Pages deployment.
- Readers do not need local setup instructions.
- The repository still contains the data pipeline and source assets used to produce the published map outputs.

## Methodology

### 1. Election Data Ingest

- Historical precinct-level election inputs are read from `data/Openelections/`.
- Official statewide files can override OpenElections for key years where present (for example 2020/2024 handling in `build_pa_data_layers.py`).
- Rows are normalized to common contest types and party buckets (`dem`, `rep`, `other`) before aggregation.

### 2. Precinct Geometry Layer Build

- `build_vtd_precinct_and_centroid_layers(...)` builds:
  - `data/Voting_Precincts.geojson`
  - `data/precinct_centroids.geojson`
- The pipeline standardizes identifiers used by the web app, including:
  - `VTD_NORM`
  - `precinct_norm`
  - `county_norm`
- `BLOCK_COUNT` is attached from block-assignment-derived counts (`data/vtd_block_counts.csv`) so precinct cards can surface structural context.

### 3. Precinct-to-VTD Matching Bridge

- `load_vtd_bridge_index()` builds county-scoped exact and loose alias indices from 2020 VTD names.
- `match_row_to_current_vtds(...)` applies normalization plus county-specific alias rules to map election rows to current VTD keys.
- This is how legacy precinct labels are reconciled with current geometry naming.

### 4. Reallocating Statewide Votes to Current District Lines

- For statewide contests in district views, votes are not blindly copied.
- The pipeline builds a `VTD -> current district` relationship using:
  - 2020 blocks (`tl_2022_42_tabblock20.zip`)
  - district geometries (CD118/SLDL/SLDU)
  - block assignment file (`BlockAssign_ST42_PA.zip`)
- `allocate_votes_by_block_counts(...)` allocates each precinct row across districts proportional to block counts, then resolves rounding via largest remainder.
- Result: districtized statewide slices that are comparable on current lines.

### 5. Actual District Races vs Reallocated Statewide Contests

- Actual district races are kept when directly available:
  - `us_house` (2022, 2024)
  - `state_house` (2022, 2024)
  - `state_senate` (2022, 2024)
- Other district-view contest displays are reallocated statewide results.
- District coverage metadata is emitted per slice (`districts_observed`, `districts_expected`, `coverage_percent`, `source`).

### 6. How Early-Year Coverage Was Reconstructed

The strong coverage in the early years was built from a constrained set of available resources rather than from one complete, stable precinct dataset. The project combines historical OpenElections exports and Pennsylvania precinct-return files with successive TIGER/VTD geography, LRC district materials, block-assignment data, and available VEST/MGGG-derived crosswalk and residual resources.

The central problem is that a precinct label is not a permanent geographic identifier. Names, codes, splits, consolidations, and district assignments change over time. The workflow therefore treats historical coverage as a geographic reconstruction problem:

1. Normalize historical contest, party, candidate, county, and precinct fields into a common schema.
2. Match legacy precinct labels to a current VTD bridge using exact names, normalized aliases, and targeted county-specific exceptions.
3. Use block-level assignments and district geometries to determine how matched VTDs relate to current congressional, state House, and state Senate lines.
4. Allocate votes across split relationships using block counts, with largest-remainder rounding so allocated totals remain consistent.
5. Track residuals and unresolved matches, preserve known exceptions, and use the best available crosswalk or source for each year rather than inventing a single universal mapping.
6. Record the resulting district-row coverage and source in each emitted contest slice so reconstructed results can be distinguished from direct district returns.

This workflow builds on the method developed for the project's Ohio coverage: establish a stable modern geography, construct historical crosswalks into that geography, use finer-grained blocks where boundaries split, and keep unresolved or residual cases explicit instead of hiding them. I then adapted that method to Pennsylvania's available source files and boundary history.

Ohio also supplied an important practical advantage: county-precinct codes were available as durable identifiers, and those codes often remained stable even when the corresponding precinct names changed. That made it possible to anchor many Ohio historical matches by code first and use names as confirmation or a diagnostic when they diverged. Pennsylvania did not provide the same uniformly stable identifier across the full historical span, so the Pennsylvania workflow required more name normalization, county-specific alias rules, geography bridges, block crosswalks, and residual review.

The project also credits the Redistricting Data Hub (RDH) and the Voting and Election Science Team (VEST) as important supporting resources. Their publicly available data products, crosswalks, and documentation were consulted—and, where appropriate, used as supplemental data—when Pennsylvania-specific source files were incomplete or a historical case was difficult to resolve. Their work helped provide reference points for checking geographic relationships and understanding how to handle the kinds of historical boundary and residual problems encountered here.

It is an applied reconstruction workflow, not a claim that every historical precinct boundary or allocation is identical to an RDH, VEST, or other proprietary production dataset.

The early-year result is therefore best understood as a layered evidence product: direct returns are used where available; historical precincts are reconciled through geography; and statewide contests are reallocated to current district lines when a direct district race is unavailable. High district-row coverage does not by itself prove perfect precinct-name matching or historical-boundary precision, which is why the repository retains source metadata, crosswalk artifacts, residual work queues, and explicit coverage caveats.

### 7. Optional Share Calibration

- If `data/district-statistics *.csv` files are present, `apply_dra_share_calibration(...)` can calibrate district shares for selected scope/contest/year combinations while preserving usable turnout totals.

### 8. Manifest-Driven Delivery

- `data/contests/manifest.json` indexes county/statewide slices.
- `data/district_contests/manifest.json` indexes district slices.
- `data/precinct_returns_manifest.json` indexes the browser-ready raw precinct-return tables and records source files, row counts, crosswalks, and matched/unmatched rows for each year.
- The frontend prioritizes manifest-based loading and only falls back to legacy aggregate payloads when needed.

### 9. Current Precinct Returns

`Scripts/build_pa_precinct_returns.py` converts Pennsylvania Department of State fixed-column exports and standardized OpenElections files into a common browser-ready table. The generated rows retain county, precinct, office, district, party, candidate, vote, Election Day, mail, and provisional fields.

The return builder uses historical or modern precinct-to-2020-VTD crosswalks first, then applies `data/crosswalks/pa_vtd20_to_current_precinct.csv` to align those VTD targets with the current precinct polygons used by the frontend. This lets the app show historical returns on a stable current geometry while preserving source and matching metadata in `data/precinct_returns_manifest.json`.

The current build covers eight general-election years (`2000`, `2004`, `2008`, `2012`, `2016`, `2020`, `2022`, and `2024`), all 67 counties, and 9,530 current voting-district features. Official Pennsylvania bulk exports take precedence when available for `2008`, `2020`, `2022`, and `2024`.

To rebuild the return tables after changing source data:

```powershell
python Scripts/build_pa_current_precinct_crosswalk.py
python Scripts/build_pa_precinct_returns.py
```

The manifest is the source of truth for which years are built and which source/crosswalk artifacts were used. Nonzero unmatched-row counts are expected for historical exports and should be treated as a coverage caveat rather than silently filled.

## How the Layers Work in the App

### Path + Hosting Logic

- `detectBasePath()` and `withBase()` in `index.html` detect GitHub Pages project-site paths (`/<repo-name>/...`) and prefix data requests accordingly.
- This is the key reason the same published app survives repo renames/path changes when configured consistently.

### Layer Stack

- County base layers:
  - `county-fill`
  - `county-stroke`
  - `county-label` (toggleable)
- Congressional layer:
  - `district-fill`
  - `district-stroke`
- State legislative layers:
  - `state-house-fill` / `state-house-stroke`
  - `state-senate-fill` / `state-senate-stroke`
- Precinct detail layers:
  - `precinct-fill` / `precinct-stroke` (polygon mode at higher zoom)
  - `precinct-dot` / `precinct-dot-missing` (centroid mode + missing-polygon fallback)

### Fill Opacity Tuning

- County fill opacity is controlled in `index.html` by `countyBaseFillOpacityStops()` and by the county contest repaint block that resets `county-fill` opacity when a contest is applied.
- Congressional and legislative fill opacity is controlled in `index.html` by `districtBaseFillOpacityStops(scope)` plus the initial paint definitions for `district-fill`, `state-house-fill`, and `state-senate-fill`.
- If you want stronger fills, increase those zoom-stop values together so startup styling and runtime contest styling stay in sync.
- County opacity intentionally stays lower while precinct overlay is enabled so precinct polygons and centroid dots remain readable.

### Contest Render Flow

- On load, the app attempts to load contest and district manifests first.
- Initial startup is intentionally county-first so the shell, map, and primary contest index become interactive before heavier district resources finish warming.
- District geometry, district metadata, and secondary reference datasets now load lazily in the background or on first entry into a district view.
- If manifests exist, selectors and map styling are built from those slice files.
- For each selected contest/year/view, the app computes color expressions and applies them directly to active fill layers.
- Shift mode requests prior-cycle data; if unavailable, the UI falls back to Margins mode to avoid false shift displays.

### What This Means for Reporting

- County view = direct county aggregation.
- District view may be:
  - direct district race results, or
  - statewide results reallocated onto current district lines.
- Always cite which mode you used when publishing conclusions.

## Data Lineage Table

| Output artifact | Built by | Primary upstream inputs | Consumed by app |
|---|---|---|---|
| `data/pa_elections_aggregated.json` | `build_election_aggregated(...)` | `data/Openelections/**`, official statewide overrides when present | County/statewide calculations and fallback flows |
| `data/contests/*.json` + `data/contests/manifest.json` | `build_contest_manifests(...)` | Aggregated statewide payload (`results_by_year`) | Contest selector + county-level contest loading |
| `data/district_contests/*.json` + `data/district_contests/manifest.json` | `build_district_manifests(...)` | Precinct rows, official district sources, VTD bridge, block-based district weights, optional DRA calibration | District views (`congressional`, `state_house`, `state_senate`) |
| `data/tileset/pa_cd118_tileset.geojson` | `build_district_tilesets()` | `data/tl_2022_42_cd118.zip` | Congress geometry source |
| `data/tileset/pa_state_house_2022_lines_tileset.geojson` | `build_district_tilesets()` | `data/tl_2022_42_sldl.zip` | State House geometry source |
| `data/tileset/pa_state_senate_2022_lines_tileset.geojson` | `build_district_tilesets()` | `data/tl_2022_42_sldu.zip` | State Senate geometry source |
| `data/Voting_Precincts.geojson` | `build_vtd_precinct_and_centroid_layers(...)` | 2020 VTD geometry + county lookup + VTD block counts | Precinct polygon overlay |
| `data/precinct_centroids.geojson` | `build_vtd_precinct_and_centroid_layers(...)` | 2020 VTD geometry transformed to representative points | Precinct dot layer and missing-polygon fallback |
| `data/vtd_block_counts.csv` | `build_vtd_block_counts_report(...)` | `data/BlockAssign_ST42_PA.zip` (`BlockAssign_ST42_PA_VTD.txt`) | Precinct metadata (`BLOCK_COUNT`) |
| `data/Openelections/*/*__pa__general__precinct.csv` | `Scripts/build_pa_precinct_returns.py` | PA official exports, standardized OpenElections files, historical/modern VTD crosswalks, current precinct crosswalk | County aggregation and precinct-return map coloring |
| `data/crosswalks/pa_vtd20_to_current_precinct.csv` | `Scripts/build_pa_current_precinct_crosswalk.py` | 2020 VTD geometry, current Pennsylvania voting-district geometry, precinct aliases | Historical-return alignment to frontend precinct polygons |
| `data/precinct_returns_manifest.json` | `Scripts/build_pa_precinct_returns.py` | Generated precinct-return tables and crosswalk metadata | Precinct-return loading, source display, and coverage checks |
| `data/pa_current_voting_districts.geojson` | Current-precinct geometry build | Current Pennsylvania voting-district source geometry | Stable frontend geometry for precinct returns |
| `data/pa_district_results_2022_lines.json` | `build_district_results_2022_lines(...)` | Synthetic placeholder payload | Legacy fallback path (explicitly disabled for synthetic district fallback) |
| `data/pa_congressional_districts.csv`, `data/pa_state_house_districts.csv`, `data/pa_state_senate_districts.csv` | `build_pa_congressional_districts(...)`, `build_state_house_csv(...)`, `build_state_senate_csv(...)` | Generated district metadata scaffolding | Sidebar district demographics/labels |
| `data/pa_district_descriptions.json` | `build_district_descriptions(...)` | Generated district description scaffolding | Tooltip/side-panel district labels |
| `data/county_demographics_2020_dp1.json` | `build_county_demographics(...)` | County geometry/name lookup + demographic source payload | County demographic display blocks |

## Matching Coverage Snapshot

Snapshot below is computed from current `data/district_contests/*.json` metadata in this repository.

| Scope | Files | Year range | Average coverage | Minimum coverage |
|---|---:|---|---:|---:|
| `congressional` | 45 | 2000-2024 | 100.00% | 100.00% |
| `state_house` | 45 | 2000-2024 | 99.98% | 99.51% |
| `state_senate` | 45 | 2000-2024 | 100.00% | 100.00% |

Current non-100% district slices:

- `state_house_governor_2018.json`: 202/203 districts (99.51%)
- `state_house_us_senate_2018.json`: 202/203 districts (99.51%)

Interpretation notes:

- Coverage here is district-row coverage in emitted slice files (`districts_observed / districts_expected`).
- It is not the same as a formal precinct-name match precision/recall audit.
- For publication-grade methodological audits, add instrumentation to log unmatched row counts by county and year during `match_row_to_current_vtds(...)`.

## Known Edge Cases in Precinct Name Matching

`match_row_to_current_vtds(...)` includes county-specific alias logic for known naming irregularities. These are the highest-touch counties/rules currently in code:

- `MONTGOMERY`: repeated district/precinct token normalization patterns plus explicit `LOWER MERION` special-case handling.
- `MONROE`: `MIDDLE SMITHFIELD` east/west reconciliation, `JACKSON` north/south split handling, and `TUNKHANNOCK` harmonization.
- `NORTHAMPTON`: targeted fixes for `LEHIGH ... PENN`, `ALLEN`, `LOWER MOUNT BETHEL`, and `UPPER MOUNT BETHEL` naming variants.
- `BUCKS`: split-token normalization (shared rule family with Montgomery) and explicit `TINICUM` typo correction.
- `DAUPHIN`: `CITY ...` prefixes mapped to `HARRISBURG ...`.
- `CARBON`: dedup fix for repeated `FRANKLIN DISTRICT FRANKLIN IND ...` token.
- `LACKAWANNA`: `SPRINGBROOK ...` to `SPRING BROOK` normalization.
- `LUZERNE`: `PLYMOUTH`/`PLYMOUTH TOWNSHIP` harmonized to districtized naming.

Important limitation:

- The pipeline currently stores deterministic correction rules, but does not emit per-county "corrections applied" counters by default.
- If you want a quantitative "top counties by alias corrections" leaderboard, instrument counters inside `match_row_to_current_vtds(...)` and write a report artifact (for example `data/matching_diagnostics.json`).

## Repository Layout

```text
.
|-- index.html
|-- build_pa_data_layers.py
|-- requirements.txt
|-- Scripts/
|   |-- build_pa_current_precinct_crosswalk.py
|   |-- build_pa_precinct_returns.py
|   |-- convert_pa_2022_precinct_returns_to_openelections.py
|   `-- convert_pa_2024_precinct_returns_to_openelections.py
`-- data/
    |-- crosswalks/
    |-- contests/
    |-- district_contests/
    |-- Openelections/
    |-- precinct_returns_manifest.json
    |-- pa_current_voting_districts.geojson
    |-- tileset/
    |-- Voting_Precincts.geojson
    |-- precinct_centroids.geojson
    `-- pa_elections_aggregated.json
```

## GitHub Pages Notes

- Keep asset paths lowercase and consistent (`data/...`).
- Project-site deployments are served under `/<repo-name>/...`.
- The app includes runtime base-path detection for `github.io` hosts.
- If map layers fail to load, check browser network requests for `404` on data assets first.

## Known Limitations

- Large raw files can make cloning/pushing slower.
- Coverage varies by year and contest type based on available source files.
- Some derived district outputs depend on crosswalk quality and matching coverage.
- Historical precinct-return alignment can leave unmatched rows when source labels cannot be reconciled to the current geometry; the per-year manifest records those counts.
- Current precinct geometry represents a stable display geography for comparison and is not a claim that historical precinct boundaries were identical.
- This repo currently has no `LICENSE` file; add one before broad public reuse.

## Candidate Name Display Normalization

Candidate-name normalization is shared between the data pipeline and frontend. Run the reusable script after changing source JSONs:

```powershell
python Scripts/candidate_name_normalizer.py data/contests data/district_contests data/pa_elections_aggregated.json
python Scripts/candidate_name_normalizer.py --check data/contests data/district_contests data/pa_elections_aggregated.json
```

Canonical labels are written consistently across county, precinct, and district layers.
The normalizer skips files whose names contain `.pre-` or `backup`, so archived snapshots are left unchanged.

- Common ordering variants are normalized to a readable canonical form (`First Last, Suffix`) when inferrable.
- `Robert P. Casey, Jr.` (and common variants like `Casey, Jr., Bob`) is normalized to `Bob Casey, Jr.` for display.
- Preferred display names are applied per candidate rather than by a blanket first-name rule (for example, `Dave Sunday`, `David H. McCormick`, and `Eugene DePasquale`).
- Short margin labels use last-name format (for example, `Casey +12.77%`) with trailing punctuation removed.

## Credits and Data Sources

- OpenElections historical election files
- Pennsylvania official election return exports
- U.S. Census TIGER/Line and related geographic inputs
- Mapbox GL JS basemap rendering

If you publish analysis from this project, include source attribution and note whether figures are direct district returns or reallocated statewide estimates.

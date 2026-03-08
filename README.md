# PAPrecinctMap

Interactive Pennsylvania election map built around 2020 VTD precinct geometry, statewide contest aggregates, and selected district-level race layers.

## What this project does

- Renders a Pennsylvania precinct map in the browser from [index.html](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\index.html).
- Uses 2020 Pennsylvania VTD precinct boundaries and derived precinct centroids.
- Supports statewide contest data from `2000` through `2024`.
- Supports current-line backcasts of statewide contests onto:
  - `Congress / CD118`
  - `State House / 2022 SLDL`
  - `State Senate / 2022 SLDU`
- Supports actual district-race slices for:
  - `U.S. House`: `2022`, `2024`
  - `State House`: `2022`, `2024`
  - `State Senate`: `2024`
- Enriches precincts with 2020 census block counts derived from the PA block assignment crosswalk.

## Current data model

### Geometry

- Precinct polygons: [data/Voting_Precincts.geojson](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\Voting_Precincts.geojson)
- Precinct centroids: [data/precinct_centroids.geojson](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\precinct_centroids.geojson)
- Counties: [data/pa_counties.geojson](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\pa_counties.geojson)
- Congressional lines: [data/tileset/pa_cd118_tileset.geojson](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\tileset\pa_cd118_tileset.geojson)
- State House lines: [data/tileset/pa_state_house_2022_lines_tileset.geojson](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\tileset\pa_state_house_2022_lines_tileset.geojson)
- State Senate lines: [data/tileset/pa_state_senate_2022_lines_tileset.geojson](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\tileset\pa_state_senate_2022_lines_tileset.geojson)

### Generated contest outputs

- Statewide contest manifest: [data/contests/manifest.json](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\contests\manifest.json)
- District contest manifest: [data/district_contests/manifest.json](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\district_contests\manifest.json)
- Aggregate statewide output: [data/pa_elections_aggregated.json](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\pa_elections_aggregated.json)

### Source election inputs

- OpenElections historical files: `data/Openelections/...`
- Official 2022 raw precinct returns:
  - [data/ElectionReturns_2022_General_PrecinctReturns.txt](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\ElectionReturns_2022_General_PrecinctReturns.txt)
- Official 2024 raw precinct export:
  - [data/erstat_2024_g_268768_20250129.txt](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\erstat_2024_g_268768_20250129.txt)
- Converted 2024 official OpenElections-style file:
  - [data/Openelections/2024/20241105__pa__general__precinct_official.csv](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\Openelections\2024\20241105__pa__general__precinct_official.csv)

## Repository structure

```text
PAPrecinctMap/
  index.html
  build_pa_data_layers.py
  requirements.txt
  Scripts/
    convert_pa_2022_precinct_returns_to_openelections.py
    convert_pa_2024_precinct_returns_to_openelections.py
  data/
    Openelections/
    contests/
    district_contests/
    tileset/
    Voting_Precincts.geojson
    precinct_centroids.geojson
    pa_counties.geojson
    ...
```

## Setup

### Python environment

This project was built with a local virtual environment in `.venv`.

Create it:

```powershell
py -m venv .venv
```

Activate it in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

## Running locally

This is a static web app. Serve the repository root with any local web server.

Example:

```powershell
python -m http.server 8000
```

Then open:

```text
http://localhost:8000/
```

Important:

- The project now uses lowercase `data/` paths intentionally.
- This matters on case-sensitive hosts like GitHub Pages.

## Build workflow

### 1. Convert official precinct exports if needed

2022:

```powershell
.\.venv\Scripts\python.exe Scripts\convert_pa_2022_precinct_returns_to_openelections.py
```

2024:

```powershell
.\.venv\Scripts\python.exe Scripts\convert_pa_2024_precinct_returns_to_openelections.py
```

### 2. Rebuild derived map layers and contest outputs

```powershell
.\.venv\Scripts\python.exe build_pa_data_layers.py
```

This regenerates the main derived outputs, including:

- `data/Voting_Precincts.geojson`
- `data/precinct_centroids.geojson`
- `data/vtd_block_counts.csv`
- `data/contests/*.json`
- `data/district_contests/*.json`
- `data/pa_elections_aggregated.json`

## What `build_pa_data_layers.py` currently does

- Builds precinct polygon and centroid layers from 2020 PA VTD geometry.
- Adds normalized VTD ids and census block counts to precinct features.
- Aggregates statewide contest results from OpenElections-style precinct inputs.
- Reallocates statewide precinct results onto current congressional and legislative lines through a `precinct -> 2020 VTD -> 2020 block -> current district` bridge.
- Builds district-race files from actual precinct-level district data where available.
- Prefers the official 2024 statewide OpenElections-style file for 2024 statewide aggregation.
- Prefers the official 2024 raw precinct export for 2024 district-race generation.

## Contest availability

### Statewide contests

Available from actual county-level aggregation for `2000-2024`:

- President
- Governor
- U.S. Senate
- Attorney General
- Secretary of State
- State Treasurer
- Auditor General

### District races

Available from actual precinct-level district data:

- U.S. House: `2022`, `2024`
- State House: `2022`, `2024`
- State Senate: `2024`

Statewide contests on district layers:

- Statewide contests selected on `Congress`, `State House`, or `State Senate` layers are backcast onto current district lines.
- These are not original historical district-boundary results.
- They are current-line reallocations built from shared precinct matching and block-based district assignment.

## Crosswalks and census block counts

This project uses the Pennsylvania block assignment file to derive a precinct-level count of 2020 census blocks in each VTD.

Relevant output:

- [data/vtd_block_counts.csv](C:\Users\Shama\OneDrive\Documents\Course_Materials\CPT-236\Side_Projects\PAPrecinctMap\data\vtd_block_counts.csv)

Relevant precinct properties:

- `VTD_NORM`
- `BLOCK_COUNT`

These are surfaced in the UI for hover and pinned precinct details.

## GitHub Pages / hosting notes

- The app is sensitive to path casing.
- Use lowercase `data/` paths consistently.
- Browser console warnings from `events.mapbox.com` blocked by an ad blocker are generally harmless.
- Browser `Permissions-Policy` warnings are not the application failure mode.
- A `404` for `data/...` assets is the real issue when geometry or contests fail to load.

## Large files

Some data files in the repository are large and may trigger GitHub warnings.

Two especially large raw Census zip inputs were intentionally excluded from tracked history because GitHub rejected them:

- `data/tl_2020_42_tabblock10.zip`
- `data/tl_2022_42_tabblock20.zip`

If you need them locally for rebuilding from raw sources, keep local copies outside normal git history or move them to Git LFS.

## Known limitations

- Some source datasets are large enough to make repo pushes slow.
- The 2024 official raw export does not expose a clean, trusted in-file mapping for vote-method splits in the converter, so the converted official OE-style file leaves `election_day`, `mail`, and `provisional` blank.
- The archived/older 2024 statewide OE file previously had vote-method splits but was not kept as the canonical root-level statewide source.
- District coverage depends on the underlying source files available for each year and office.
- Historical districtized statewide results depend on the quality of the precinct-to-`2020 VTD` bridge for each source year and county.

## Suggested next improvements

- Add a UI indicator for district coverage/source metadata.
- Merge official 2024 totals with method-split data into one canonical 2024 precinct file.
- Add a small deployment section for GitHub Pages publishing.
- Move remaining `>50 MB` files to Git LFS if repo size becomes a problem.

## License / data usage

No project license file is included yet. If this repo is going to stay public, add a license and brief attribution notes for:

- OpenElections data
- Census TIGER/Line geometry inputs
- Pennsylvania official returns files
- Mapbox basemap usage

import csv, json
from pathlib import Path
import re
import zipfile
from collections import Counter, defaultdict
try:
    import geopandas as gpd
except Exception:  # pragma: no cover
    gpd = None

base = Path('.')

data_dir = base / 'data'
( data_dir / 'district_contests').mkdir(parents=True, exist_ok=True)
( data_dir / 'contests').mkdir(parents=True, exist_ok=True)
( data_dir / 'tileset').mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------
# 1) Build district info CSVs and district descriptions JSON with realistic placeholders
# ------------------------------------------------------------
def build_pa_congressional_districts(path: Path):
    rows = []
    for d in range(1, 18):
        rows.append({
            'district': str(d),
            'total_population': 700000,
            'white_vap_pct': 75,
            'black_vap_pct': 8,
            'hispanic_vap_pct': 7,
            'asian_vap_pct': 4,
            'name': f'Congressional District {d}',
        })
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['district', 'total_population', 'white_vap_pct', 'black_vap_pct', 'hispanic_vap_pct', 'asian_vap_pct', 'name'])
        w.writeheader()
        w.writerows(rows)


def build_state_house_csv(path: Path, total=203):
    rows = []
    for d in range(1, total + 1):
        rows.append({
            'district': str(d),
            'total_population': 62000,
            'white_vap_pct': 78,
            'black_vap_pct': 7,
            'hispanic_vap_pct': 6,
            'asian_vap_pct': 4,
            'name': f'State House District {d}',
        })
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['district', 'total_population', 'white_vap_pct', 'black_vap_pct', 'hispanic_vap_pct', 'asian_vap_pct', 'name'])
        w.writeheader()
        w.writerows(rows)


def build_state_senate_csv(path: Path, total=50):
    rows = []
    for d in range(1, total + 1):
        rows.append({
            'district': str(d),
            'total_population': 255000,
            'white_vap_pct': 80,
            'black_vap_pct': 9,
            'hispanic_vap_pct': 6,
            'asian_vap_pct': 3,
            'name': f'State Senate District {d}',
        })
    with path.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['district', 'total_population', 'white_vap_pct', 'black_vap_pct', 'hispanic_vap_pct', 'asian_vap_pct', 'name'])
        w.writeheader()
        w.writerows(rows)


def build_district_descriptions(path: Path):
    payload = {
        'congressional': {str(i): f'PA Congressional District {i}' for i in range(1, 18)},
        'state_house': {str(i): f'PA State House District {i}' for i in range(1, 204)},
        'state_senate': {str(i): f'PA State Senate District {i}' for i in range(1, 51)},
    }
    with path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)


# ------------------------------------------------------------
# 2) Copy county demographics placeholders from available county names (if precinct/county geojson exists)
# ------------------------------------------------------------
def normalize_county_name(name: str) -> str:
    return re.sub(r'\s+COUNTY$', '', (name or '').upper().strip())


def apply_official_county_party_controls(rows, year: int, controls_dir=None, contest_types=None):
    """Reconcile precinct rows to certified county party buckets in place.

    Each county/contest/party residual stays inside the source rows that created
    that bucket. Largest remainder makes the adjusted rows integral and exact;
    no residual is spread statewide or moved between counties.
    """
    controls_dir = Path(controls_dir or (data_dir / 'benchmarks'))
    controls = {}
    contest_types = set(contest_types or [])
    for path in sorted(controls_dir.glob(f'pa_county_{int(year)}_*_certified.csv')):
        contest = path.stem[len(f'pa_county_{int(year)}_'):-len('_certified')]
        if contest_types and contest not in contest_types:
            continue
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            for control in csv.DictReader(handle):
                county = normalize_county_name(control.get('county') or '')
                if not county:
                    continue
                controls[(contest, county, 'dem')] = safe_int(control.get('dem_votes'))
                controls[(contest, county, 'rep')] = safe_int(control.get('rep_votes'))
                controls[(contest, county, 'other')] = safe_int(control.get('other_votes'))
    if not controls:
        return rows

    grouped = defaultdict(list)
    for index, row in enumerate(rows):
        contest = office_mapping_for_contest(row.get('office') or '')
        county = normalize_county_name(row.get('county') or '')
        party = (row.get('party') or '').strip().upper()
        bucket = 'dem' if party in PARTY_DEM or party == 'YES' else 'rep' if party in PARTY_REP or party == 'NO' else 'other'
        if (contest, county, bucket) in controls:
            grouped[(contest, county, bucket)].append(index)

    missing = sorted(key for key, target in controls.items() if target and key not in grouped)
    if missing:
        raise RuntimeError(f'Certified county controls have no source rows: {missing[:10]}')

    for key, indices in grouped.items():
        target = int(controls[key])
        weights = [max(safe_float(rows[index].get('votes')), 0.0) for index in indices]
        source_total = sum(weights)
        if source_total <= 0:
            if target:
                raise RuntimeError(f'Cannot allocate nonzero certified county control {key}: {target}')
            allocations = [0] * len(indices)
        else:
            raw = [target * weight / source_total for weight in weights]
            allocations = [int(value) for value in raw]
            remainder = target - sum(allocations)
            order = sorted(range(len(indices)), key=lambda pos: (raw[pos] - allocations[pos], -pos), reverse=True)
            for pos in order[:remainder]:
                allocations[pos] += 1
        for index, votes in zip(indices, allocations):
            rows[index]['votes'] = votes
    return rows


def load_county_features(path: Path):
    with path.open('r', encoding='utf-8') as f:
        data = json.load(f)
    feats = data.get('features', []) if isinstance(data, dict) else []
    return [f for f in feats if isinstance(f, dict)]


def county_names_from_data_geojson(path: Path):
    county_names = []
    if not path.exists():
        return county_names
    try:
        feats = load_county_features(path)
    except Exception:
        return county_names
    for feat in feats:
        props = feat.get('properties', {}) if isinstance(feat, dict) else {}
        for key in ('NAME', 'name', 'COUNTY', 'county', 'NAME10', 'NAMELSAD'):
            val = (props.get(key) or '').strip() if isinstance(props.get(key, ''), str) else ''
            if val:
                county_names.append(normalize_county_name(val).upper())
                break
    county_names = [c for c in county_names if c]
    # Preserve deterministic ordering from source geometry
    unique = []
    seen = set()
    for c in county_names:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    return unique


def build_county_demographics(base_county_path: Path, out_path: Path):
    feats = load_county_features(base_county_path)
    counties = {}
    for f in feats:
        props = f.get('properties', {}) or {}
        raw = props.get('NAME') or props.get('county') or props.get('COUNTY') or props.get('NAME10') or ''
        county = normalize_county_name(str(raw))
        if not county:
            continue
        counties[county] = {
            'county': county,
            'total_population': 150000,
            'white_vap_pct': 82,
            'black_vap_pct': 7,
            'hispanic_vap_pct': 5,
            'asian_vap_pct': 3,
            'n_hispanic_vap_pop': 7500,
            'n_white_vap_pop': 123000,
            'n_black_vap_pop': 10500,
        }
    payload = {'counties': counties}
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)


def load_county_lookup_from_geojson(path: Path):
    if not path.exists() or gpd is None:
        return {}
    try:
        geodf = gpd.read_file(path)
    except Exception:
        return {}

    countyfp_col = None
    for candidate in ('COUNTYFP20', 'COUNTYFP', 'COUNTYFP10'):
        if candidate in geodf.columns:
            countyfp_col = candidate
            break
    county_name_col = None
    for candidate in ('NAME20', 'county', 'NAME', 'NAMELSAD20'):
        if candidate in geodf.columns:
            county_name_col = candidate
            break
    if not countyfp_col or not county_name_col:
        return {}

    lookup = {}
    for _, row in geodf.iterrows():
        raw_fp = (row.get(countyfp_col) or '').strip() if isinstance(row.get(countyfp_col), str) else str(row.get(countyfp_col, '')).strip()
        if not raw_fp:
            continue
        county = (row.get(county_name_col) or '').strip()
        if not county:
            continue
        lookup[raw_fp.zfill(3)] = county.upper().replace(' COUNTY', '')
    return lookup


def normalize_vtd_code(value):
    text = ('' if value is None else str(value)).strip()
    if not text:
        return ''
    if text.isdigit():
        return text.zfill(6)
    return text.upper().replace(' ', '')


def load_vtd_block_counts_from_blockassign(zip_path: Path, assignment_filename: str):
    if not zip_path.exists():
        return {}

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            if assignment_filename not in z.namelist():
                return {}
            raw = z.read(assignment_filename).decode('utf-8', errors='ignore')
    except Exception:
        return {}

    rows = raw.splitlines()
    if not rows:
        return {}

    header = [h.strip() for h in rows[0].split('|')]
    try:
        dist_idx = header.index('DISTRICT')
    except ValueError:
        return {}

    counts = {}
    for line in rows[1:]:
        if not line:
            continue
        parts = line.split('|')
        if len(parts) <= dist_idx:
            continue
        dist = normalize_vtd_code(parts[dist_idx])
        if not dist:
            continue
        counts[dist] = counts.get(dist, 0) + 1
    return counts


def build_vtd_block_counts_report(out_path: Path, counts: dict):
    if out_path.exists() or not counts:
        return
    with out_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['DISTRICT', 'BLOCK_COUNT'])
        writer.writeheader()
        for dist in sorted(counts, key=str):
            writer.writerow({'DISTRICT': dist, 'BLOCK_COUNT': counts[dist]})


def build_vtd_precinct_and_centroid_layers(vtd_zip: Path, county_lookup: dict, precinct_out: Path, centroid_out: Path, block_counts_by_vtd=None):
    if gpd is None or not vtd_zip.exists():
        return
    if precinct_out.exists() and centroid_out.exists():
        return

    try:
        geodf = gpd.read_file(vtd_zip)
    except Exception:
        return

    countyfp_col = None
    vtd_col = None
    for candidate in ('COUNTYFP20', 'COUNTYFP'):
        if candidate in geodf.columns:
            countyfp_col = candidate
            break
    for candidate in ('VTDST20', 'VTD', 'VTDST'):
        if candidate in geodf.columns:
            vtd_col = candidate
            break
    if not countyfp_col or not vtd_col:
        return

    def normalize_county_fp(v):
        text = str(v or '').strip()
        return text.zfill(3) if text else ''

    county_name = geodf[countyfp_col].apply(lambda v: county_lookup.get(normalize_county_fp(v), '')).fillna('')
    geodf['COUNTYFP20'] = geodf[countyfp_col].astype(str).str.zfill(3)
    geodf['COUNTYFP'] = geodf['COUNTYFP20']
    geodf['VTD'] = geodf[vtd_col].astype(str).str.strip()
    geodf['VTD_NORM'] = geodf['VTD'].apply(normalize_vtd_code)
    geodf['VTDST'] = geodf['VTD']
    geodf['prec_id'] = geodf['VTD']
    geodf['county_nam'] = county_name
    geodf['county_norm'] = geodf['county_nam'].str.upper().str.replace(r'[^A-Z0-9 .\-]', '', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip()
    # TIGER's NAME20/NAMELSAD20 values are the human-readable precinct labels
    # used by the atlas-style geometry pattern. Keep the stable VTD code as the fallback.
    source_name_col = 'NAME20' if 'NAME20' in geodf.columns else ('NAMELSAD20' if 'NAMELSAD20' in geodf.columns else None)
    geodf['precinct_name'] = geodf[source_name_col].fillna('').astype(str).str.strip() if source_name_col else geodf['VTD']
    geodf.loc[geodf['precinct_name'].eq(''), 'precinct_name'] = geodf.loc[geodf['precinct_name'].eq(''), 'VTD']
    geodf['precinct_norm'] = (county_name + ' - ' + geodf['VTD']).str.upper().str.replace(r'[^A-Z0-9 .\-]', '', regex=True).str.replace(r'\s+', ' ', regex=True).str.strip()
    geodf['BLOCK_COUNT'] = geodf['VTD_NORM'].map(lambda k: int(block_counts_by_vtd.get(k, 0)) if isinstance(block_counts_by_vtd, dict) else 0)
    geodf['id'] = None

    # Preserve a compact, map-friendly geometry payload.
    if not precinct_out.exists():
        geodf[['geometry', 'COUNTYFP20', 'COUNTYFP', 'VTD', 'VTD_NORM', 'VTDST', 'prec_id', 'precinct_name', 'precinct_norm', 'county_nam', 'county_norm', 'BLOCK_COUNT']].to_file(precinct_out, driver='GeoJSON')

    if centroid_out.exists():
        return
    centroids = geodf.copy()
    centroids['geometry'] = centroids.geometry.centroid
    centroids[['geometry', 'COUNTYFP20', 'COUNTYFP', 'VTD', 'VTD_NORM', 'VTDST', 'prec_id', 'precinct_name', 'precinct_norm', 'county_nam', 'county_norm', 'BLOCK_COUNT']].to_file(centroid_out, driver='GeoJSON')


# ------------------------------------------------------------
# 3) Create minimal election aggregate JSON from available county results in OpenElections csvs
# ------------------------------------------------------------
DATA_ROOT = base / 'data' / 'Openelections'

PARTY_DEM = {'DEM', 'D', 'DEMOCRATIC', 'DEMOCRAT'}
PARTY_REP = {'REP', 'R', 'REPUBLICAN'}
STATEWIDE_CONTEST_TYPES = [
    'president', 'governor', 'us_senate', 'attorney_general',
    'secretary_of_state', 'treasurer', 'auditor',
    'supreme_court', 'superior_court', 'commonwealth_court',
]
DISTRICT_SCOPE_BY_CONTEST = {
    'us_house': 'congressional',
    'state_house': 'state_house',
    'state_senate': 'state_senate',
}
CURRENT_SCOPE_DISTRICT_MAX = {
    'congressional': 17,
    'state_house': 203,
    'state_senate': 50,
}
EXPECTED_DISTRICT_COUNT = {
    'congressional': 17,
    'state_house': 203,
    'state_senate': 50,
}
OFFICIAL_2024_STATEWIDE_OE_SOURCE = DATA_ROOT / '2024' / '20241105__pa__general__precinct_official.csv'
OFFICIAL_2020_STATEWIDE_SOURCE = base / 'data' / 'ElectionReturns_2020_General_PrecinctReturns.txt'
OFFICIAL_JUDICIAL_SOURCES = {
    2001: base / 'data' / 'ElectionReturns_2001_Municipal_PrecinctReturns.txt',
    2003: base / 'data' / 'ElectionReturns_2003_Municipal_PrecinctReturns.txt',
    2007: base / 'data' / 'ElectionReturns_2007_Municipal_PrecinctReturns.txt',
    2011: base / 'data' / 'ElectionReturns_2011_General_PrecinctReturns.txt',
    2015: base / 'data' / 'ElectionReturns_2015_Municipal_Precinct.txt',
    2017: base / 'data' / 'ElectionReturns_2017_Municipal_PrecinctReturns.txt',
    2019: base / 'data' / 'ElectionReturns_2019_General_PrecinctReturns.txt',
    2021: base / 'data' / 'ElectionReturns_2021_Municipal_PrecinctReturns.txt',
    2023: base / 'data' / 'ElectionReturns_2023_Municipal_PrecinctReturns.txt',
    2025: base / 'data' / 'ElectionReturns_2025_Municipal_PrecinctReturns.txt',
}
SUPPLEMENTAL_JUDICIAL_SOURCES = {
    2011: [
        DATA_ROOT / '2011' / 'supplemental' / 'philadelphia_2011_supreme_retention.csv',
        DATA_ROOT / '2011' / 'supplemental' / 'philadelphia_2011_other_retention.csv',
        DATA_ROOT / '2011' / 'supplemental' / 'lackawanna_2011_supreme_retention.csv',
        DATA_ROOT / '2011' / 'supplemental' / 'lackawanna_2011_other_retention.csv',
        DATA_ROOT / '2011' / 'supplemental' / 'montour_2011_all_retention.csv',
        DATA_ROOT / '2011' / 'supplemental' / 'greene_2011_all_retention.csv',
    ],
}
OFFICIAL_2024_DISTRICT_SOURCE = base / 'data' / 'erstat_2024_g_268768_20250129.txt'
DRA_DISTRICT_STATS_FILENAME = re.compile(
    r'^district-statistics\s+(state house|state senate)\s+(\d{4})\s+(.+?)\.csv$',
    flags=re.I
)
DRA_SCOPE_LABEL_TO_SCOPE = {
    'state house': 'state_house',
    'state senate': 'state_senate',
}
DRA_CONTEST_TOKEN_TO_CONTEST = {
    'pres': 'president',
    'president': 'president',
}
RAW_OFFICE_CODE_MAP = {
    'USP': 'President',
    'USS': 'U.S. Senate',
    'GOV': 'Governor',
    'ATT': 'Attorney General',
    'AUD': 'Auditor General',
    'TRE': 'State Treasurer',
    'USC': 'U.S. House',
    'STH': 'State House',
    'STS': 'State Senate',
    'SPM': 'Supreme Court',
    'SPR': 'Superior Court',
    'CCJ': 'Commonwealth Court',
}
COUNTY_FIPS_BY_NAME = None
VTD_BRIDGE_INDEX = None
VTD_CURRENT_DISTRICT_BLOCKS = None
VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = None
RAW_COUNTY_NAME_BY_FIPS = None
CURRENT_PRECINCT_TO_VTDS = None
PRECINCT_ALIAS_VTDS = None
MAINTAINED_PRECINCT_TARGETS = None
MAINTAINED_PRECINCT_PARENT_SOURCES = None
HISTORICAL_VTD10_TARGETS = None

# Reviewed one-to-one legacy labels whose A/B or "Independent" suffix is not
# represented as a separate Carter VTD. Targets were checked against all three
# BEF-backed block maps; ambiguous municipality parents are intentionally absent.
REVIEWED_LEGACY_VTD_EXCEPTIONS = {
    ('ALLEGHENY', 'ELIZABETH WARD 5 DISTRICT 1'): ('003', '002022'),
    ('BERKS', 'CUMRU DISTRICT 1 B'): ('011', '000240'),
    ('BERKS', 'LAURELDALE DISTRICT 1 B'): ('011', '000530'),
    ('CLARION', 'PINEY P'): ('031', '000340'),
    ('HUNTINGDON', 'PENN P'): ('061', '000380'),
    ('HUNTINGDON', 'PENN P B'): ('061', '000380'),
    ('LACKAWANNA', 'OLYPHANT WARD 3 DISTRICT 2 A'): ('069', '001209'),
    ('LEBANON', 'NORTH LEBANON DISTRICT EAST B'): ('075', '000350'),
    ('MONTGOMERY', 'BRYN ATHYN INDEPENDENT'): ('091', '000460'),
    ('MONTGOMERY', 'PERKIOMEN DISTRICT 1 B'): ('091', '002195'),
    ('MONTGOMERY', 'PLYMOUTH DISTRICT 2 DISTRICT 3B'): ('091', '002488'),
    ('MONTGOMERY', 'PLYMOUTH DISTRICT 2 DISTRICT 3C'): ('091', '002488'),
    # These legacy labels either identify an exact surviving VTD or fall
    # wholly within a municipality whose candidate VTD20s have the same
    # CD118/SLDL22/SLDU22 signature.  The representative VTD therefore does
    # not guess across a 2022 district boundary.
    ('DELAWARE', 'CONCORD DISTRICT CENTRAL EAST'): ('045', '000816'),
    ('DELAWARE', 'CONCORD DISTRICT CENTRAL WEST'): ('045', '000816'),
    ('DELAWARE', 'CONCORD DISTRICT FOXHILL'): ('045', '000816'),
    ('DELAWARE', 'CONCORD DISTRICT MARIS GROVE'): ('045', '000816'),
    ('DELAWARE', 'CONCORD DISTRICT SOUTHCENTRAL'): ('045', '000816'),
    ('DELAWARE', 'CONCORD DISTRICT SOUTHWEST'): ('045', '000816'),
    ('ERIE', 'GIRARD DISTRICT EAST'): ('049', '000890'),
    ('ERIE', 'KEAN DISTRICT EAST'): ('049', '001068'),
    ('ERIE', 'KEAN DISTRICT WEST'): ('049', '001068'),
    ('MONTGOMERY', 'HATFIELD DISTRICT 5 DISTRICT 2 A'): ('091', '001036'),
    ('MONTGOMERY', 'HATFIELD DISTRICT 5 DISTRICT 2 B'): ('091', '001036'),
    # OpenPrecincts PA18G documents Horsham 2-2 A/B as obsolete
    # congressional fragments recombined to Horsham 2-2; the maintained
    # Carter/alias target for that precinct is VTD20 001085.
    ('MONTGOMERY', 'HORSHAM DISTRICT 2 B'): ('091', '001085'),
    ('MONTGOMERY', 'MARLBOROUGH A'): ('091', '001997'),
    ('MONTGOMERY', 'UPPER DUBLIN DISTRICT 6 DISTRICT 3B'): ('091', '003141'),
    ('MONTGOMERY', 'WHITPAIN DISTRICT 1 92'): ('091', '003812'),
    ('NORTHUMBERLAND', 'RIVERSIDE P'): ('097', '000560'),
    ('TIOGA', 'SHIPPEN P'): ('117', '000350'),
    ('TIOGA', 'SHIPPEN P B'): ('117', '000350'),
}


def iter_openelections_csvs():
    years = sorted([int(p.name) for p in DATA_ROOT.iterdir() if p.is_dir() and p.name.isdigit() and 2000 <= int(p.name) <= 2024])
    for y in years:
        year_dir = DATA_ROOT / str(y)
        if y == 2020 and OFFICIAL_2020_STATEWIDE_SOURCE.exists():
            yield y, OFFICIAL_2020_STATEWIDE_SOURCE
            continue
        if y == 2024 and OFFICIAL_2024_STATEWIDE_OE_SOURCE.exists():
            files = [OFFICIAL_2024_STATEWIDE_OE_SOURCE]
            for fp in files:
                yield y, fp
            continue
        statewide_files = sorted(year_dir.glob('*__pa__general__precinct.csv'))
        county_dir = year_dir / 'counties'
        if statewide_files:
            files = statewide_files
        elif county_dir.exists():
            files = sorted(county_dir.glob('*__pa__general__*__precinct.csv'))
        else:
            files = sorted(year_dir.glob('*__pa__general__*__precinct.csv'))
        for fp in files:
            yield y, fp

    for y in sorted(OFFICIAL_JUDICIAL_SOURCES):
        year_dir = DATA_ROOT / str(y)
        normalized = sorted(year_dir.glob('*__pa__municipal__precinct.csv'))
        # Prefer the official export: unlike the normalized derivative, it
        # retains the county-local historical VTD/precinct code needed by the
        # NHGIS block-chain crosswalk. The normalized file remains a fallback.
        if OFFICIAL_JUDICIAL_SOURCES[y].exists():
            yield y, OFFICIAL_JUDICIAL_SOURCES[y]
        elif normalized:
            for fp in normalized:
                yield y, fp
        for supplemental in SUPPLEMENTAL_JUDICIAL_SOURCES.get(y, []):
            if supplemental.exists():
                yield y, supplemental


def read_csv_rows(path: Path):
    with path.open('r', encoding='utf-8-sig', errors='ignore') as f:
        text = f.read()
    rows = []
    lines = text.splitlines()
    if not lines:
        return rows
    first = [p.strip().strip('"') for p in lines[0].split(',')]
    if first and first[0].isdigit() and (len(first) < 2 or first[1].upper() in {'G', 'M', 'P', 'S'}):
        rows = infer_missing_parties(read_raw_precinct_rows(lines))
        return [row for row in rows if not is_summary_result_row(row)]
    header = [h.strip() for h in lines[0].split(',')]
    idx = {h:i for i,h in enumerate(header)}
    for line in lines[1:]:
        if not line.strip():
            continue
        raw = []
        cur = ''
        in_q = False
        for ch in line:
            if ch == '"':
                in_q = not in_q
            elif ch == ',' and not in_q:
                raw.append(cur)
                cur = ''
            else:
                cur += ch
        raw.append(cur)
        while len(raw) < len(header):
            raw.append('')
        row = {header[i]: raw[i].strip().strip('"') for i in range(len(header))}
        rows.append(row)
    rows = infer_missing_parties(rows)
    return [row for row in rows if not is_summary_result_row(row)]


def raw_county_name_lookup():
    global RAW_COUNTY_NAME_BY_FIPS
    if RAW_COUNTY_NAME_BY_FIPS is not None:
        return RAW_COUNTY_NAME_BY_FIPS
    lookup = {}
    path = base / 'Data' / 'pa_counties.geojson'
    try:
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        for feature in data.get('features', []):
            props = feature.get('properties', {}) or {}
            fips = str(props.get('COUNTYFP20') or props.get('COUNTYFP') or '').zfill(3)
            name = (props.get('NAME20') or props.get('NAME') or '').strip()
            if fips and name:
                lookup[fips] = name
    except Exception:
        lookup = {}
    RAW_COUNTY_NAME_BY_FIPS = lookup
    return RAW_COUNTY_NAME_BY_FIPS


def read_raw_precinct_rows(lines):
    rows = []
    county_lookup = raw_county_name_lookup()
    for raw in csv.reader(lines):
        if not raw:
            continue
        raw = [part.strip().strip('"') for part in raw]
        if len(raw) < 29:
            continue
        office_code = (raw[8] or '').strip().upper()
        office = RAW_OFFICE_CODE_MAP.get(office_code)
        if not office:
            continue
        county_fips = ''
        if len(raw) >= 35 and str(raw[29]).isdigit():
            county_fips = str(raw[29]).zfill(3)
        elif len(raw) >= 28 and str(raw[27]).isdigit():
            county_fips = str(raw[27]).zfill(3)
        county = county_lookup.get(county_fips, county_fips)
        source_vtd = ''
        source_vtd_raw = raw[30] if len(raw) >= 35 else raw[28] if len(raw) >= 29 else ''
        source_vtd_raw = str(source_vtd_raw or '').strip().upper()
        if re.fullmatch(r'[0-9A-Z]+', source_vtd_raw):
            # Maintained historical crosswalks retain PA's short alpha IDs
            # (for example Pittsburgh A020) but zero-pad numeric VTD codes.
            source_vtd = source_vtd_raw.zfill(6) if source_vtd_raw.isdigit() else source_vtd_raw
        name_start = 22 if len(raw) >= 35 else 20
        precinct = ' '.join(part for part in raw[name_start:name_start + 5] if part).strip()
        district = ''
        if office_code == 'USC':
            district = raw[18].strip() if len(raw) >= 37 else raw[16].strip()
        elif office_code == 'STS':
            district = raw[19].strip() if len(raw) >= 37 else raw[17].strip()
        elif office_code == 'STH':
            district = raw[20].strip() if len(raw) >= 37 else raw[18].strip()
        if len(raw) >= 37:
            precinct_cd = raw[34].strip()
            precinct_sldu = raw[35].strip()
            precinct_sldl = raw[36].strip()
        elif len(raw) >= 33:
            precinct_cd = raw[30].strip()
            precinct_sldu = raw[31].strip()
            precinct_sldl = raw[32].strip()
        else:
            precinct_cd = ''
            precinct_sldu = ''
            precinct_sldl = ''
        candidate = ' '.join(part for part in [raw[12], raw[13], raw[11], raw[14]] if part).strip().title() or 'Write Ins'
        parsed_row = {
            'county': county,
            'precinct': precinct,
            'source_vtd': source_vtd,
            'office': office,
            'district': district,
            'congressional_district': precinct_cd,
            'state_senate_district': precinct_sldu,
            'state_house_district': precinct_sldl,
            'party': (raw[9] or '').strip(),
            'candidate': candidate,
            'votes': (raw[15] or '').strip(),
        }
        # Retention questions encode YES and NO in separate columns on one
        # official-export row. Expand them to ordinary OpenElections-style
        # candidate rows so no votes are discarded during normalization.
        is_retention = (
            office_code in {'SPM', 'SPR', 'CCJ'}
            and not (raw[9] or '').strip()
            and len(raw) > 17
            and ((raw[16] or '').strip() or (raw[17] or '').strip())
        )
        if is_retention:
            retention_office = f'{office} Retention - {candidate}'
            yes_row = dict(parsed_row, office=retention_office, party='YES', candidate='Yes', votes=(raw[16] or '').strip())
            no_row = dict(parsed_row, office=retention_office, party='NO', candidate='No', votes=(raw[17] or '').strip())
            rows.extend([yes_row, no_row])
        else:
            rows.append(parsed_row)
    return rows


def is_summary_result_row(row):
    candidate = re.sub(r'\s+', ' ', (row.get('candidate') or '').strip()).upper()
    return candidate in {'CAST VOTES', 'OVER VOTES', 'UNDER VOTES', 'TOTAL VOTES'}


def infer_missing_parties(rows):
    if not rows:
        return rows
    party_by_office_candidate = {}
    counts = defaultdict(int)
    surname_counts = defaultdict(int)

    def candidate_surname_key(candidate: str):
        head = re.split(r'/', (candidate or '').upper(), maxsplit=1)[0]
        parts = [re.sub(r'[^A-Z]', '', token) for token in re.split(r'[\s,]+', head) if token.strip()]
        parts = [part for part in parts if part]
        while parts and parts[-1] in {'JR', 'SR', 'II', 'III', 'IV', 'V'}:
            parts.pop()
        return parts[-1] if parts else ''

    for row in rows:
        office = (row.get('office') or '').strip().upper()
        candidate = (row.get('candidate') or '').strip().upper()
        party = (row.get('party') or '').strip().upper()
        if not office or not candidate or not party:
            continue
        key = (office, candidate, party)
        counts[key] += 1
        surname = candidate_surname_key(candidate)
        if surname:
            surname_counts[(office, surname, party)] += 1
    best = {}
    for (office, candidate, party), count in counts.items():
        oc = (office, candidate)
        cur = best.get(oc)
        if cur is None or count > cur[1]:
            best[oc] = (party, count)
    best_by_surname = {}
    for (office, surname, party), count in surname_counts.items():
        oc = (office, surname)
        cur = best_by_surname.get(oc)
        if cur is None or count > cur[1]:
            best_by_surname[oc] = (party, count)
    for row in rows:
        party = (row.get('party') or '').strip()
        if party:
            continue
        office = (row.get('office') or '').strip().upper()
        candidate = (row.get('candidate') or '').strip().upper()
        if not office or not candidate:
            continue
        inferred = best.get((office, candidate))
        if not inferred:
            inferred = best_by_surname.get((office, candidate_surname_key(candidate)))
        if inferred:
            row['party'] = inferred[0]
    return rows


def office_mapping_for_contest(office: str):
    o = re.sub(r'\s+', ' ', (office or '').strip().lower())
    retention = re.match(r'^(supreme|superior|commonwealth) court retention - (.+)$', o)
    if retention:
        court, justice = retention.groups()
        return f'{court}_court_retention_{re.sub(r"[^a-z0-9]+", "_", justice).strip("_")}'
    if 'president' in o:
        return 'president'
    if o == 'governor':
        return 'governor'
    if o in ('u.s. senate', 'us senate', 'us senator', 'us sen', 'senate'):
        return 'us_senate'
    if o in ('attorney general', 'attorney_general'):
        return 'attorney_general'
    if o == 'secretary of state':
        return 'secretary_of_state'
    if o in ('state treasurer', 'treasurer'):
        return 'treasurer'
    if o in ('auditor general', 'auditor'):
        return 'auditor'
    if o in ('u.s. house', 'us house', 'representative in congress'):
        return 'us_house'
    if o in ('state house', 'state assembly', 'general assembly', 'representative in the general assembly'):
        return 'state_house'
    if o == 'state senate':
        return 'state_senate'
    if o in ('supreme court', 'justice of the supreme court') or o.startswith('supreme court retention -'):
        return 'supreme_court'
    if o in ('superior court', 'judge of the superior court') or o.startswith('superior court retention -'):
        return 'superior_court'
    if o in ('commonwealth court', 'judge of the commonwealth court') or o.startswith('commonwealth court retention -'):
        return 'commonwealth_court'
    return None


def is_statewide_contest_type(contest_type):
    return contest_type in STATEWIDE_CONTEST_TYPES or bool(re.match(
        r'^(supreme|superior|commonwealth)_court_retention_[a-z0-9_]+$', contest_type or ''
    ))


def safe_int(value):
    try:
        return int(float((value or 0)))
    except Exception:
        return 0


def safe_float(value):
    try:
        return float((value or 0))
    except Exception:
        return 0.0


def round_fractional_vote_components(node):
    """Round accumulated party components once while preserving their total."""
    raw = {
        field: max(float(node.get(field) or 0), 0.0)
        for field in ('dem_votes', 'rep_votes', 'other_votes')
    }
    target_total = int(round(sum(raw.values())))
    rounded = {field: int(value) for field, value in raw.items()}
    remainder = target_total - sum(rounded.values())
    if remainder > 0:
        priority = {'dem_votes': 3, 'rep_votes': 2, 'other_votes': 1}
        order = sorted(
            raw,
            key=lambda field: (raw[field] - rounded[field], priority[field]),
            reverse=True,
        )
        for field in order[:remainder]:
            rounded[field] += 1
    return rounded, target_total


def normalized_vote_shares(dem_share, rep_share, other_share):
    shares = [max(safe_float(v), 0.0) for v in (dem_share, rep_share, other_share)]
    if any(v > 1.0 for v in shares):
        shares = [v / 100.0 for v in shares]
    total = sum(shares)
    if total <= 0:
        return None
    return tuple(v / total for v in shares)


def allocate_votes_by_shares(total_votes: int, dem_share: float, rep_share: float, other_share: float):
    total_votes = max(int(total_votes or 0), 0)
    if total_votes <= 0:
        return {'dem_votes': 0, 'rep_votes': 0, 'other_votes': 0}
    shares = normalized_vote_shares(dem_share, rep_share, other_share)
    if not shares:
        return None
    keys = ['dem_votes', 'rep_votes', 'other_votes']
    raw = {
        'dem_votes': total_votes * shares[0],
        'rep_votes': total_votes * shares[1],
        'other_votes': total_votes * shares[2],
    }
    allocated = {k: int(raw[k]) for k in keys}
    remainder = total_votes - sum(allocated.values())
    if remainder > 0:
        priority = {k: len(keys) - i for i, k in enumerate(keys)}
        order = sorted(
            keys,
            key=lambda k: (raw[k] - allocated[k], priority[k]),
            reverse=True
        )
        for k in order[:remainder]:
            allocated[k] += 1
    return allocated


def normalize_district_id(raw):
    text = (raw or '').strip()
    if not text:
        return ''
    match = re.search(r'\d+', text)
    if not match:
        return ''
    return str(int(match.group(0)))


def expected_district_count(scope: str, contest_type: str, year: int):
    if scope == 'congressional':
        if contest_type != 'us_house' or int(year) >= 2022:
            return 17
        return EXPECTED_DISTRICT_COUNT[scope]
    if scope == 'state_senate' and contest_type == 'state_senate':
        return 25
    return EXPECTED_DISTRICT_COUNT.get(scope, 0)


def district_assignment_for_scope(row, scope: str):
    max_district = CURRENT_SCOPE_DISTRICT_MAX.get(scope, 0)
    def clean(value):
        district_id = normalize_district_id(value or '')
        if not district_id or not str(district_id).isdigit():
            return ''
        district_num = int(district_id)
        if district_num <= 0 or (max_district and district_num > max_district):
            return ''
        return str(district_num)
    if scope == 'congressional':
        return clean(row.get('congressional_district') or '')
    if scope == 'state_house':
        return clean(row.get('state_house_district') or '')
    if scope == 'state_senate':
        return clean(row.get('state_senate_district') or '')
    return ''


def embedded_congressional_district_from_precinct_label(label: str):
    text = (label or '').strip()
    if not text:
        return ''
    match = re.search(r'\((?:USC|CONG)\s*(\d+)\)', text, flags=re.I)
    if not match:
        return ''
    district_num = int(match.group(1))
    if district_num <= 0 or district_num > CURRENT_SCOPE_DISTRICT_MAX.get('congressional', 0):
        return ''
    return str(district_num)


def county_fips_by_name():
    global COUNTY_FIPS_BY_NAME
    if COUNTY_FIPS_BY_NAME is not None:
        return COUNTY_FIPS_BY_NAME
    lookup = {}
    for fips, name in raw_county_name_lookup().items():
        norm = normalize_county_name(name)
        if norm:
            lookup[norm] = fips
    COUNTY_FIPS_BY_NAME = lookup
    return COUNTY_FIPS_BY_NAME


def normalize_bridge_precinct_name(name: str):
    s = (name or '').upper().strip()
    if not s:
        return ''
    ordinal_words = {
        'FIRST': '1', 'SECOND': '2', 'THIRD': '3', 'FOURTH': '4', 'FIFTH': '5',
        'SIXTH': '6', 'SEVENTH': '7', 'EIGHTH': '8', 'NINTH': '9', 'TENTH': '10',
        'ELEVENTH': '11', 'TWELFTH': '12', 'THIRTEENTH': '13', 'FOURTEENTH': '14',
        'FIFTEENTH': '15', 'SIXTEENTH': '16', 'SEVENTEENTH': '17', 'EIGHTEENTH': '18',
        'NINETEENTH': '19', 'TWENTIETH': '20',
        'ONE': '1', 'TWO': '2', 'THREE': '3', 'FOUR': '4', 'FIVE': '5',
        'SIX': '6', 'SEVEN': '7', 'EIGHT': '8', 'NINE': '9', 'TEN': '10',
    }
    for word, num in ordinal_words.items():
        s = re.sub(rf'\b{word}\b', f' {num} ', s)
    s = re.sub(r'\([^)]*\)', ' ', s)
    s = re.sub(r'^(?:\d+[A-Z]?|[IVXLCDM]+)(?:[-\s]+(?:\d+[A-Z]?|[IVXLCDM]+))*\s+(?=[A-Z])', '', s)
    s = s.replace('&', ' AND ')
    s = s.replace('#', ' DISTRICT ')
    s = s.replace('~', ' ')
    s = re.sub(r'\bCENTRE\b', ' CENTRAL ', s)
    s = re.sub(r'\bCENTER\b', ' CENTRAL ', s)
    s = re.sub(r'\bTWP\b\.?', ' TOWNSHIP ', s)
    s = re.sub(r'\bBORO\b\.?', ' BOROUGH ', s)
    s = re.sub(r'\bBR\b\.?', ' BOROUGH ', s)
    s = re.sub(r'\bMT\b\.?', ' MOUNT ', s)
    s = re.sub(r'\bPCT\b\.?', ' PRECINCT ', s)
    s = re.sub(r'\bDIS\b\.?', ' DISTRICT ', s)
    s = re.sub(r'\bDIV\b\.?', ' DIVISION ', s)
    s = re.sub(r'\bDIST\b\.?', ' DISTRICT ', s)
    s = re.sub(r'\bWD\b\.?', ' WARD ', s)
    s = re.sub(r'\bW\b', ' WARD ', s)
    s = re.sub(r'\bD\b', ' DISTRICT ', s)
    s = re.sub(r'\bX\b', ' DISTRICT ', s)
    s = re.sub(r'\bNO\b\.?\s+(\d+)\b', r' DISTRICT \1 ', s)
    s = re.sub(r'\b([0-9]+)(ST|ND|RD|TH)\b', r'\1', s)
    s = re.sub(r'\bW[\s\-]*(\d+)\b', r' WARD \1 ', s)
    s = re.sub(r'\bP[\s\-]*(\d+)\b', r' PRECINCT \1 ', s)
    s = re.sub(r'\bD[\s\-]*(\d+)\b', r' DISTRICT \1 ', s)
    s = re.sub(r'\bP[\s\-]*NE\b', ' DISTRICT NORTHEAST ', s)
    s = re.sub(r'\bP[\s\-]*NW\b', ' DISTRICT NORTHWEST ', s)
    s = re.sub(r'\bP[\s\-]*SE\b', ' DISTRICT SOUTHEAST ', s)
    s = re.sub(r'\bP[\s\-]*SW\b', ' DISTRICT SOUTHWEST ', s)
    s = re.sub(r'\bP[\s\-]*SO\b', ' DISTRICT SOUTH ', s)
    s = re.sub(r'\b(\d+)W\b', r' WARD \1 ', s)
    s = re.sub(r'\b(\d+)P\b', r' PRECINCT \1 ', s)
    s = re.sub(r'\b(\d+)D\b', r' DISTRICT \1 ', s)
    s = re.sub(r'\b(?:DISTRICT\s+)?\d+\s+CONGRESSIONAL\b', ' ', s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'\b(WARD|DISTRICT|PRECINCT)\s+([A-Z0-9]+)\s+\1\s+\2\b', r' \1 \2 ', s)
    s = re.sub(r'[^A-Z0-9]+', ' ', s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r'^(.*?)\s+((?:WARD|DISTRICT|PRECINCT)\s+[A-Z0-9]+(?:\s+[A-Z0-9]+)*)\s+\2$', r'\1 \2', s)
    s = re.sub(r'\b0+(\d+)\b', lambda m: str(int(m.group(1))), s)
    return re.sub(r'\s+', ' ', s).strip()


def bridge_precinct_aliases(name: str):
    base = normalize_bridge_precinct_name(name)
    if not base:
        return set()
    aliases = {base}
    for value in list(aliases):
        aliases.add(re.sub(r'\bVOTING DISTRICT\b', '', value).strip())
        aliases.add(re.sub(r'\bPRECINCT\b', '', value).strip())
        aliases.add(re.sub(r'\bDISTRICT (?=\d)', '', value).strip())
        aliases.add(re.sub(r'\b(TOWNSHIP|BOROUGH|CITY|TOWN)\b', '', value).strip())
        aliases.add(re.sub(r'\bCITY\b', '', value).strip())
    m = re.match(r'^(\d+)\s+(\d+)$', base)
    if m:
        ward = str(int(m.group(1)))
        precinct = str(int(m.group(2)))
        aliases.update({
            f'WARD {ward} PRECINCT {precinct}',
            f'PHILADELPHIA WARD {ward} PRECINCT {precinct}',
            f'WARD {ward.zfill(2)} PRECINCT {precinct.zfill(2)}',
            f'PHILADELPHIA WARD {ward.zfill(2)} PRECINCT {precinct.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+(\d+)\s+(PRECINCT|DISTRICT)\s+(\d+)$', base)
    if m:
        ward = str(int(m.group(2)))
        unit = m.group(3)
        part = str(int(m.group(4)))
        other = 'DISTRICT' if unit == 'PRECINCT' else 'PRECINCT'
        aliases.update({
            f'WARD {ward} {unit} {part}',
            f'WARD {ward.zfill(2)} {unit} {part.zfill(2)}',
            f'WARD {ward} {other} {part}',
            f'WARD {ward.zfill(2)} {other} {part.zfill(2)}',
            f'{ward} {part}',
        })
    m = re.match(r'^(.*?)\s+(\d+)\s+WARD\s+(\d+)\s+(PRECINCT|DISTRICT)$', base)
    if m:
        stem = m.group(1).strip()
        ward = str(int(m.group(2)))
        part = str(int(m.group(3)))
        unit = m.group(4)
        aliases.update({
            f'{stem} WARD {ward} {unit} {part}',
            f'{stem} WARD {ward.zfill(2)} {unit} {part.zfill(2)}',
            f'WARD {ward} {unit} {part}',
            f'{ward} {part}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+(\d+)$', base)
    if m:
        ward = str(int(m.group(2)))
        aliases.update({
            f'WARD {ward}',
            f'WARD {ward.zfill(2)}',
            f'{ward} W',
        })
    m = re.match(r'^(.*?)\s+(\d+)\s+WARD$', base)
    if m:
        stem = m.group(1).strip()
        ward = str(int(m.group(2)))
        aliases.update({
            f'{stem} WARD {ward}',
            f'{stem} WARD {ward.zfill(2)}',
            f'WARD {ward}',
        })
    m = re.match(r'^(.*?)\s+(PRECINCT|DISTRICT)\s+(\d+)$', base)
    if m:
        unit = m.group(2)
        part = str(int(m.group(3)))
        other = 'DISTRICT' if unit == 'PRECINCT' else 'PRECINCT'
        aliases.update({
            f'{unit} {part}',
            f'{unit} {part.zfill(2)}',
            f'{other} {part}',
            f'{other} {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(\d+)\s+(PRECINCT|DISTRICT)$', base)
    if m:
        stem = m.group(1).strip()
        part = str(int(m.group(2)))
        unit = m.group(3)
        other = 'DISTRICT' if unit == 'PRECINCT' else 'PRECINCT'
        aliases.update({
            f'{stem} {unit} {part}',
            f'{stem} {unit} {part.zfill(2)}',
            f'{stem} {other} {part}',
            f'{stem} {other} {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        part = str(int(m.group(2)))
        aliases.update({
            f'{stem} WARD {part}',
            f'{stem} DISTRICT {part}',
            f'{stem} PRECINCT {part}',
            f'{stem} WARD {part.zfill(2)}',
            f'{stem} DISTRICT {part.zfill(2)}',
            f'{stem} PRECINCT {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(TOWNSHIP|BOROUGH|CITY|TOWN)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        part = str(int(m.group(3)))
        aliases.update({
            f'{stem} WARD {part}',
            f'{stem} DISTRICT {part}',
            f'{stem} PRECINCT {part}',
            f'{stem} WARD {part.zfill(2)}',
            f'{stem} DISTRICT {part.zfill(2)}',
            f'{stem} PRECINCT {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(NORTH|SOUTH|EAST|WEST|UPPER|LOWER|MIDDLE|CENTRAL|NORTHERN|SOUTHERN)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        side = m.group(2).strip()
        part = str(int(m.group(3)))
        aliases.update({
            f'{stem} DISTRICT {side} {part}',
            f'{stem} {side} DISTRICT {part}',
            f'{stem} DISTRICT {side} DIVISION {part}',
            f'{stem} WARD {side} {part}',
            f'{stem} PRECINCT {side} {part}',
            f'{stem} DISTRICT {side} {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+((?:NORTH|SOUTH|EAST|WEST|UPPER|LOWER|MIDDLE|CENTRAL|NORTHERN|SOUTHERN)\s+(?:NORTH|SOUTH|EAST|WEST|UPPER|LOWER|MIDDLE|CENTRAL|NORTHERN|SOUTHERN))\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        side = m.group(2).strip()
        part = str(int(m.group(3)))
        aliases.update({
            f'{stem} DISTRICT {side} {part}',
            f'{stem} DISTRICT {side} DIVISION {part}',
            f'{stem} {side} DISTRICT {part}',
            f'{stem} {side} DIVISION {part}',
            f'{stem} DISTRICT {side} {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(TOWNSHIP|BOROUGH|CITY|TOWN)\s+(\d+)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        part_a = str(int(m.group(3)))
        part_b = str(int(m.group(4)))
        aliases.update({
            f'{stem} WARD {part_a} PRECINCT {part_b}',
            f'{stem} WARD {part_a.zfill(2)} PRECINCT {part_b.zfill(2)}',
            f'{stem} DISTRICT {part_a} DIVISION {part_b}',
            f'{stem} DISTRICT {part_a.zfill(2)} DIVISION {part_b.zfill(2)}',
            f'{stem} DISTRICT {part_a}{part_b}',
            f'{stem} DISTRICT {part_a.zfill(2)}{part_b.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(\d+)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        part_a = str(int(m.group(2)))
        part_b = str(int(m.group(3)))
        aliases.update({
            f'{stem} WARD {part_a} PRECINCT {part_b}',
            f'{stem} WARD {part_a.zfill(2)} PRECINCT {part_b.zfill(2)}',
            f'{stem} DISTRICT {part_a} PRECINCT {part_b}',
            f'{stem} DISTRICT {part_a.zfill(2)} PRECINCT {part_b.zfill(2)}',
            f'{stem} DISTRICT {part_a} DIVISION {part_b}',
            f'{stem} DISTRICT {part_a.zfill(2)} DIVISION {part_b.zfill(2)}',
            f'{stem} DISTRICT {part_a}{part_b}',
            f'{stem} DISTRICT {part_a.zfill(2)}{part_b.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+(\d+)\s+([A-Z0-9]+)$', base)
    if m:
        stem = m.group(1).strip()
        ward = str(int(m.group(2)))
        part = m.group(3).strip()
        aliases.update({
            f'{stem} WARD {ward}',
            f'{stem} WARD {ward.zfill(2)}',
            f'{stem} WARD {ward} DISTRICT {part}',
            f'{stem} WARD {ward.zfill(2)} DISTRICT {part}',
            f'{stem} WARD {ward} {part}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+(\d+)\s+([A-Z]+)\s+([A-Z]+)$', base)
    if m:
        stem = m.group(1).strip()
        ward = str(int(m.group(2)))
        side = f'{m.group(3).strip()} {m.group(4).strip()}'
        side_compact = side.replace(' ', '')
        aliases.update({
            f'{stem} WARD {ward} DISTRICT {side}',
            f'{stem} WARD {ward} DISTRICT {side_compact}',
            f'{stem} WARD {ward} {side}',
            f'{stem} WARD {ward.zfill(2)} DISTRICT {side}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+0\s+PRECINCT\s+(\d+)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        part_a = str(int(m.group(2)))
        part_b = str(int(m.group(3)))
        bare_stem = re.sub(r'\b(TOWNSHIP|BOROUGH|CITY|TOWN)\b', '', stem).strip()
        aliases.update({
            f'{stem} DISTRICT {part_a} DISTRICT {part_b}',
            f'{stem} DISTRICT {part_a.zfill(2)} DISTRICT {part_b.zfill(2)}',
            f'{bare_stem} DISTRICT {part_a} DISTRICT {part_b}',
            f'{bare_stem} DISTRICT {part_a.zfill(2)} DISTRICT {part_b.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+0\s+PRECINCT\s+0$', base)
    if m:
        stem = m.group(1).strip()
        aliases.update({
            stem,
            re.sub(r'\b(TOWNSHIP|BOROUGH|CITY|TOWN)\b', '', stem).strip(),
        })
    m = re.match(r'^(.*?)\s+WARD\s+(\d+)\s+PRECINCT\s+0$', base)
    if m:
        stem = m.group(1).strip()
        ward = str(int(m.group(2)))
        aliases.update({
            f'{stem} WARD {ward}',
            f'{stem} WARD {ward.zfill(2)}',
            f'WARD {ward}',
            f'{stem} DISTRICT {ward}',
            f'{stem} DISTRICT {ward.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+WARD\s+0\s+DISTRICT\s+([A-Z]+)$', base)
    if m:
        stem = m.group(1).strip()
        side = m.group(2).strip()
        aliases.update({
            f'{stem} DISTRICT {side}',
            re.sub(r'\b(TOWNSHIP|BOROUGH|CITY|TOWN)\b', '', f'{stem} DISTRICT {side}').strip(),
        })
    m = re.match(r'^(.*?)\s+(\d+)\s+WARD$', base)
    if m:
        stem = m.group(1).strip()
        ward = str(int(m.group(2)))
        aliases.update({
            f'{stem} DISTRICT {ward}',
            f'{stem} DISTRICT {ward.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+(NORTHERN|SOUTHERN|EASTERN|WESTERN)$', base)
    if m:
        stem = m.group(1).strip()
        side = {
            'NORTHERN': 'NORTH',
            'SOUTHERN': 'SOUTH',
            'EASTERN': 'EAST',
            'WESTERN': 'WEST',
        }.get(m.group(2), m.group(2))
        aliases.update({
            f'{stem} DISTRICT {side}',
            f'{stem} {side}',
        })
    m = re.match(r'^(.*?)\s+(NORTH|SOUTH|EAST|WEST|UPPER|LOWER|MIDDLE|CENTRAL|INDEPENDENT)$', base)
    if m:
        stem = m.group(1).strip()
        side = m.group(2).strip()
        aliases.update({
            f'{stem} DISTRICT {side}',
            f'{stem} {side}',
        })
    m = re.match(r'^(.*?)\s+(NORTH|SOUTH|EAST|WEST)\s+(EAST|WEST)$', base)
    if m:
        stem = m.group(1).strip()
        side = f'{m.group(1*0+2).strip()} {m.group(3).strip()}'
        side_compact = side.replace(' ', '')
        aliases.update({
            f'{stem} DISTRICT {side}',
            f'{stem} DISTRICT {side_compact}',
            f'{stem} {side}',
        })
    m = re.match(r'^(.*?)\s+([A-Z]+(?:\s+[A-Z]+)*)\s+(PRECINCT|DISTRICT|WARD)$', base)
    if m:
        stem = m.group(1).strip()
        tail = m.group(2).strip()
        unit = m.group(3)
        aliases.update({
            f'{stem} {unit} {tail}',
            f'{stem} {tail}',
        })
    m = re.match(r'^(.*?)\s+([A-Z]+(?:\s+[A-Z]+)*)\s+(\d+)$', base)
    if m:
        stem = m.group(1).strip()
        tail = m.group(2).strip()
        part = str(int(m.group(3)))
        aliases.update({
            f'{stem} DISTRICT {tail} DISTRICT {part}',
            f'{stem} DISTRICT {tail} DISTRICT {part.zfill(2)}',
            f'{stem} DISTRICT {tail} DIVISION {part}',
            f'{stem} DISTRICT {tail} DIVISION {part.zfill(2)}',
            f'{stem} DISTRICT {tail} {part}',
            f'{stem} DISTRICT {tail} {part.zfill(2)}',
        })
    m = re.match(r'^(.*?)\s+([A-Z]+(?:\s+[A-Z]+)*)$', base)
    if m:
        stem = m.group(1).strip()
        tail = m.group(2).strip()
        aliases.update({
            f'{stem} DISTRICT {tail}',
            f'{stem} {tail}',
        })
    m = re.match(r'^(.*?)\s+(TOWNSHIP|BOROUGH|CITY|TOWN)\s+([A-Z]+(?:\s+[A-Z]+)*)$', base)
    if m:
        stem = m.group(1).strip()
        tail = m.group(3).strip()
        aliases.update({
            f'{stem} DISTRICT {tail}',
            f'{stem} WARD {tail}',
            f'{stem} PRECINCT {tail}',
            f'{stem} {tail}',
        })
    normalized_aliases = set()
    for value in list(aliases):
        if not value or not value.strip():
            continue
        candidates = {
            value,
            re.sub(r'\bVOTING DISTRICT\b', '', value).strip(),
            re.sub(r'\bPRECINCT\b', '', value).strip(),
            re.sub(r'\bDISTRICT (?=\d)', '', value).strip(),
            re.sub(r'\b(TOWNSHIP|BOROUGH|CITY|TOWN)\b', '', value).strip(),
            re.sub(r'\bCITY\b', '', value).strip(),
        }
        for candidate in candidates:
            cleaned = re.sub(r'\s+', ' ', candidate).strip()
            if cleaned:
                normalized_aliases.add(cleaned)
    return normalized_aliases


def load_vtd_bridge_index():
    global VTD_BRIDGE_INDEX
    if VTD_BRIDGE_INDEX is not None:
        return VTD_BRIDGE_INDEX
    index = defaultdict(lambda: {'exact': defaultdict(set), 'loose': defaultdict(set)})
    if gpd is None:
        VTD_BRIDGE_INDEX = index
        return VTD_BRIDGE_INDEX
    gdf = gpd.read_file('zip://data/tl_2020_42_vtd20.zip')
    for _, row in gdf.iterrows():
        countyfp = str(row.get('COUNTYFP20') or '').zfill(3)
        vtd = str(row.get('VTDST20') or '').strip()
        if not countyfp or not vtd:
            continue
        exact_names = {
            normalize_bridge_precinct_name(row.get('NAME20') or ''),
            normalize_bridge_precinct_name(row.get('NAMELSAD20') or '')
        }
        for alias in [a for a in exact_names if a]:
            index[countyfp]['exact'][alias].add(vtd)
        for source_name in [row.get('NAME20') or '', row.get('NAMELSAD20') or '']:
            for alias in bridge_precinct_aliases(source_name):
                index[countyfp]['loose'][alias].add(vtd)
    VTD_BRIDGE_INDEX = index
    return VTD_BRIDGE_INDEX


def load_vtd_current_district_equivalency_blocks():
    """Join Carter-adjusted block-to-VTD IDs to current district equivalents."""
    sources = {
        'congressional': ('42_PA_CD118.txt', 'CDFP'),
        'state_house': ('42_PA_SLDL22.txt', 'SLDLST'),
        'state_senate': ('42_PA_SLDU22.txt', 'SLDUST'),
    }
    vtd_source = data_dir / 'crosswalks' / 'pa_block20_to_vtd20.csv'
    if not vtd_source.exists() or not all((data_dir / filename).exists() for filename, _ in sources.values()):
        return None

    vtd_by_block = {}
    with vtd_source.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if not {'block', 'countyfp_dst', 'dst_vtd'}.issubset(reader.fieldnames or []):
            raise ValueError(f'Unexpected columns in {vtd_source}')
        for row in reader:
            block_id = (row.get('block') or '').strip()
            countyfp = (row.get('countyfp_dst') or '').strip().zfill(3)
            vtd = (row.get('dst_vtd') or '').strip()
            if not re.fullmatch(r'42\d{13}', block_id) or not re.fullmatch(r'\d{3}', countyfp) or not vtd:
                raise ValueError(f'Invalid Carter-adjusted VTD assignment for {block_id}')
            if block_id in vtd_by_block:
                raise ValueError(f'Duplicate Carter-adjusted VTD assignment for {block_id}')
            vtd_by_block[block_id] = (countyfp, vtd)

    block_ids = set(vtd_by_block)
    weights = {}
    for scope, (filename, district_field) in sources.items():
        scope_weights = defaultdict(lambda: defaultdict(int))
        seen = set()
        with (data_dir / filename).open('r', encoding='utf-8-sig', newline='') as handle:
            reader = csv.DictReader(handle, skipinitialspace=True)
            if not {'GEOID', district_field}.issubset(reader.fieldnames or []):
                raise ValueError(f'Unexpected columns in {filename}')
            for row in reader:
                block_id = (row.get('GEOID') or '').strip()
                if block_id in seen or block_id not in block_ids:
                    raise ValueError(f'Duplicate or unknown block {block_id} in {filename}')
                district = normalize_district_id(row.get(district_field) or '')
                if not district or not 1 <= int(district) <= CURRENT_SCOPE_DISTRICT_MAX[scope]:
                    raise ValueError(f'Invalid district for block {block_id} in {filename}')
                seen.add(block_id)
                scope_weights[vtd_by_block[block_id]][district] += 1
        if seen != block_ids:
            raise ValueError(f'{filename} is missing {len(block_ids - seen)} block assignments')
        weights[scope] = scope_weights
    return weights


def load_vtd_current_district_blocks():
    global VTD_CURRENT_DISTRICT_BLOCKS, VTD_CURRENT_SCOPE_BLOCK_WEIGHTS
    if VTD_CURRENT_DISTRICT_BLOCKS is not None:
        return VTD_CURRENT_DISTRICT_BLOCKS
    weights = {scope: defaultdict(lambda: defaultdict(int)) for scope in ('congressional', 'state_house', 'state_senate')}
    if VTD_CURRENT_SCOPE_BLOCK_WEIGHTS is None:
        VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = load_vtd_current_district_equivalency_blocks()
    if VTD_CURRENT_SCOPE_BLOCK_WEIGHTS is None and gpd is not None:
        try:
            block_gdf = gpd.read_file(f'zip://{(data_dir / "tl_2022_42_tabblock20.zip").resolve()}')[['GEOID20', 'geometry']].copy()
            equal_area_crs = 'EPSG:5070'
            block_gdf = block_gdf.to_crs(equal_area_crs)
            block_points = block_gdf[['GEOID20', 'geometry']].copy()
            block_points['geometry'] = block_points.geometry.representative_point()
            scope_sources = {
                'congressional': ('tl_2022_42_cd118.zip', 'CD118FP'),
                'state_house': ('tl_2022_42_sldl.zip', 'SLDLST'),
                'state_senate': ('tl_2022_42_sldu.zip', 'SLDUST'),
            }
            vtd_by_block = {}
            with zipfile.ZipFile(base / 'data' / 'BlockAssign_ST42_PA.zip') as z:
                with z.open('BlockAssign_ST42_PA_VTD.txt') as f:
                    next(f, None)
                    for raw_line in f:
                        line = raw_line.decode('utf-8', errors='ignore').strip()
                        if not line:
                            continue
                        parts = line.split('|')
                        if len(parts) < 3:
                            continue
                        blockid, countyfp, vtd = parts[0], parts[1].zfill(3), parts[2].strip()
                        if blockid and countyfp and vtd:
                            vtd_by_block[blockid] = (countyfp, vtd)
            block_weights = {}
            for scope, (zip_name, district_field) in scope_sources.items():
                district_gdf = gpd.read_file(f'zip://{(data_dir / zip_name).resolve()}')[[district_field, 'geometry']].copy()
                district_gdf = district_gdf.to_crs(equal_area_crs)
                joined = gpd.sjoin(block_points, district_gdf, how='left', predicate='within')
                scope_weights = defaultdict(lambda: defaultdict(int))
                max_district = CURRENT_SCOPE_DISTRICT_MAX[scope]
                for _, row in joined.iterrows():
                    blockid = str(row.get('GEOID20') or '').strip()
                    vtd_key = vtd_by_block.get(blockid)
                    if not vtd_key:
                        continue
                    district = normalize_district_id(row.get(district_field) or '')
                    if not district:
                        continue
                    district_num = int(district)
                    if district_num <= 0 or district_num > max_district:
                        continue
                    scope_weights[vtd_key][str(district_num)] += 1
                block_weights[scope] = scope_weights
            VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = block_weights
        except Exception:
            VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = {}
    for scope, scope_weights in (VTD_CURRENT_SCOPE_BLOCK_WEIGHTS or {}).items():
        weights[scope] = scope_weights
    VTD_CURRENT_DISTRICT_BLOCKS = weights
    return VTD_CURRENT_DISTRICT_BLOCKS


def collapse_repeated_precinct_suffix(value: str):
    """Collapse export artifacts such as ``HALFMOON P EAST P EAST``."""
    tokens = re.sub(r'\s+', ' ', str(value or '').upper()).strip().split()
    for start in range(1, len(tokens)):
        suffix = tokens[start:]
        if len(suffix) >= 2 and len(suffix) % 2 == 0:
            half = len(suffix) // 2
            if suffix[:half] == suffix[half:]:
                return ' '.join(tokens[:start] + suffix[:half])
    return ' '.join(tokens)


def load_maintained_precinct_targets():
    """Load reviewed historical/modern precinct-to-VTD20 crosswalks."""
    global MAINTAINED_PRECINCT_TARGETS, MAINTAINED_PRECINCT_PARENT_SOURCES
    if MAINTAINED_PRECINCT_TARGETS is not None:
        return MAINTAINED_PRECINCT_TARGETS
    index = defaultdict(list)
    for filename in ('pa_historical_precinct_to_vtd20.csv', 'pa_modern_precinct_to_vtd20.csv'):
        path = data_dir / 'crosswalks' / filename
        if not path.exists():
            continue
        with path.open('r', encoding='utf-8-sig', newline='') as handle:
            for row in csv.DictReader(handle):
                year = safe_int(row.get('year'))
                county = str(row.get('countyfp') or '').strip().zfill(3)
                raw_source = collapse_repeated_precinct_suffix(row.get('source_precinct') or '')
                source_aliases = {
                    raw_source,
                    collapse_repeated_precinct_suffix(normalize_bridge_precinct_name(raw_source)),
                }
                dst_county = str(row.get('dst_countyfp') or '').strip().zfill(3)
                dst_vtd = str(row.get('dst_vtd') or '').strip()
                try:
                    weight = float(row.get('weight') or 0)
                except (TypeError, ValueError):
                    weight = 0.0
                if year and county and dst_county and dst_vtd and weight > 0:
                    for source in source_aliases:
                        if source:
                            index[(year, county, source)].append((dst_county, dst_vtd, weight, row.get('method') or filename))
    parent_sources = defaultdict(set)
    for target_year, target_county, target_source in index:
        tokens = target_source.split()
        for end in range(1, len(tokens)):
            parent_sources[(target_year, target_county, ' '.join(tokens[:end]))].add(target_source)
    MAINTAINED_PRECINCT_TARGETS = index
    MAINTAINED_PRECINCT_PARENT_SOURCES = parent_sources
    return MAINTAINED_PRECINCT_TARGETS


def maintained_targets_for_row(row, year: int, countyfp: str):
    index = load_maintained_precinct_targets()
    parent_sources = MAINTAINED_PRECINCT_PARENT_SOURCES or {}
    source = collapse_repeated_precinct_suffix(normalize_bridge_precinct_name(row.get('precinct') or ''))
    raw_source = collapse_repeated_precinct_suffix(row.get('precinct') or '')
    candidate_years = [year]
    if year % 2:
        candidate_years.extend([year + 1, year - 1])
    source_vtd = str(row.get('source_vtd') or '').strip().upper()
    # Some normalized OpenElections Philadelphia rows concatenate county FIPS
    # and ward/precinct (for example ``PHILADELPHIA 1014903``).  Recover the
    # 2010 VTD code so the existing NHGIS block chain can place it; this is an
    # exact decoding, not a fuzzy name match.
    if not source_vtd and countyfp == '101':
        embedded = re.search(r'\b101(\d{4})$', source)
        if embedded:
            source_vtd = embedded.group(1).zfill(6)
    for candidate_year in candidate_years:
        if source_vtd.isdigit():
            source_vtd = source_vtd.zfill(6)
        for candidate_source in (source_vtd, raw_source, source):
            targets = index.get((candidate_year, countyfp, candidate_source)) or []
            if targets:
                total = sum(item[2] for item in targets) or 1.0
                return [
                    (
                        county,
                        vtd,
                        weight / total,
                        f'adjacent_{candidate_year}_{method}'
                        if candidate_year != year and candidate_source == source_vtd
                        else method,
                    )
                    for county, vtd, weight, method in targets
                ]
    # Official odd-year files retain VTD10 codes even when no election-year
    # row exists in the maintained precinct crosswalk. Resolve those codes
    # through the local NHGIS-derived 2010->2020 block chain directly.
    global HISTORICAL_VTD10_TARGETS
    if year >= 2010 and source_vtd:
        if HISTORICAL_VTD10_TARGETS is None:
            HISTORICAL_VTD10_TARGETS = defaultdict(list)
            chain_path = data_dir / 'crosswalks' / 'pa_vtd10_to_vtd20_block_chain.csv'
            if chain_path.exists():
                with chain_path.open('r', encoding='utf-8-sig', newline='') as handle:
                    for item in csv.DictReader(handle):
                        src_county = str(item.get('countyfp') or '').strip().zfill(3)
                        src_vtd = str(item.get('src_vtd') or '').strip()
                        dst_county = str(item.get('dst_countyfp') or '').strip().zfill(3)
                        dst_vtd = str(item.get('dst_vtd') or '').strip()
                        try:
                            weight = float(item.get('weight') or 0)
                        except (TypeError, ValueError):
                            weight = 0.0
                        if src_county and src_vtd and dst_county and dst_vtd and weight > 0:
                            HISTORICAL_VTD10_TARGETS[(src_county, src_vtd)].append(
                                (dst_county, dst_vtd, weight, 'vtd10_nhgis_block_chain')
                            )
        targets = HISTORICAL_VTD10_TARGETS.get((countyfp, source_vtd)) or []
        if targets:
            total = sum(item[2] for item in targets) or 1.0
            return [(county, vtd, weight / total, method) for county, vtd, weight, method in targets]
    # Odd-year judicial exports sometimes report a municipality/ward parent
    # while the adjacent even-year crosswalk has its child precincts. Expand
    # only explicit structural parents and let block counts weight the child
    # VTDs; do not apply this to arbitrary short place names.
    if year >= 2017 and year % 2:
        for candidate_year in (year + 1, year - 1):
            structural_parent = bool(re.search(r'\b(?:DISTRICT|WARD|TOWNSHIP|PRECINCT)$', source))
            parent_keys = {source}
            if structural_parent:
                parent_keys.add(re.sub(r'\s+(?:DISTRICT|WARD|TOWNSHIP|PRECINCT)$', '', source).strip())
            matching_sources = set().union(*(
                parent_sources.get((candidate_year, countyfp, parent_key), set())
                for parent_key in parent_keys if parent_key
            ))
            if structural_parent or len(matching_sources) >= 2:
                targets = {
                    (dst_county, dst_vtd)
                    for target_source in matching_sources
                    for dst_county, dst_vtd, _weight, _method in index[(candidate_year, countyfp, target_source)]
                }
            else:
                targets = set()
            if targets:
                weight = 1.0 / len(targets)
                return [
                    (dst_county, dst_vtd, weight, 'adjacent_modern_parent_block_count')
                    for dst_county, dst_vtd in sorted(targets)
                ]
    return []


def match_row_to_current_vtds(row):
    county = normalize_county_name(row.get('county') or '')
    countyfp = county_fips_by_name().get(county)
    if not countyfp:
        return []
    precinct = row.get('precinct') or ''
    if not precinct:
        return []
    reviewed_key = (county, normalize_bridge_precinct_name(precinct))
    reviewed_target = REVIEWED_LEGACY_VTD_EXCEPTIONS.get(reviewed_key)
    if reviewed_target:
        return [reviewed_target]
    # Normalized OpenElections outputs already carry the current precinct id
    # (for example ``ADAMS - 001010``). Resolve it back to the source VTD20
    # keys used by the block-to-district allocator instead of name-matching it
    # against historical VTD labels.
    global CURRENT_PRECINCT_TO_VTDS
    if CURRENT_PRECINCT_TO_VTDS is None:
        CURRENT_PRECINCT_TO_VTDS = defaultdict(set)
        crosswalk_path = data_dir / 'crosswalks' / 'pa_vtd20_to_current_precinct.csv'
        if crosswalk_path.exists():
            with crosswalk_path.open('r', encoding='utf-8-sig', newline='') as handle:
                for item in csv.DictReader(handle):
                    current_county = str(item.get('current_countyfp') or '').zfill(3)
                    current_vtd = str(item.get('current_vtd') or '').strip()
                    source_county = str(item.get('countyfp') or '').zfill(3)
                    source_vtd = str(item.get('vtd20') or '').strip()
                    if current_county and current_vtd and source_county and source_vtd:
                        CURRENT_PRECINCT_TO_VTDS[(current_county, current_vtd)].add((source_county, source_vtd))
    # Current Pennsylvania precinct IDs are not uniformly numeric. Allegheny
    # uses identifiers such as 003A000; rejecting the letter caused hundreds
    # of otherwise exact rows to fall through to fragile name matching.
    canonical = re.search(r'\b([0-9][0-9A-Z]{5,})$', str(precinct).strip().upper())
    if canonical:
        source_keys = CURRENT_PRECINCT_TO_VTDS.get((countyfp, canonical.group(1))) or set()
        if source_keys:
            return sorted(source_keys)
    # Consult the maintained alias index before the narrower Census VTD-name
    # bridge. It contains reviewed legacy spellings and split-precinct labels
    # derived from precinct_friendly_names.json and resolves directly to
    # VTD20 IDs within the named county.
    global PRECINCT_ALIAS_VTDS
    if PRECINCT_ALIAS_VTDS is None:
        PRECINCT_ALIAS_VTDS = {}
        alias_path = data_dir / 'precinct_alias_index.json'
        if alias_path.exists():
            try:
                payload = json.loads(alias_path.read_text(encoding='utf-8'))
                PRECINCT_ALIAS_VTDS = payload.get('counties') or {}
            except (OSError, json.JSONDecodeError):
                PRECINCT_ALIAS_VTDS = {}
    county_aliases = PRECINCT_ALIAS_VTDS.get(county) or {}
    alias_matches = set()
    alias_candidates = {
        str(precinct).strip().upper(),
        normalize_bridge_precinct_name(precinct),
    }
    alias_candidates.update(bridge_precinct_aliases(precinct))
    # Some official exports use D for both municipality district and its
    # nested election division (for example RAPHO D ELM TREE D II). Add only
    # exact maintained-index variants with a later DISTRICT -> DIVISION
    # substitution; no similarity or prefix matching is involved.
    for alias in list(alias_candidates):
        starts = [match.start() for match in re.finditer(r'\bDISTRICT\b', alias)]
        for start in starts[1:]:
            alias_candidates.add(alias[:start] + 'DIVISION' + alias[start + len('DISTRICT'):])
    for alias in alias_candidates:
        alias_matches.update(county_aliases.get(alias, []))
        compact = re.sub(r'[^A-Z0-9]', '', alias)
        if compact:
            alias_matches.update(county_aliases.get(compact, []))
    if alias_matches:
        return [(countyfp, str(vtd).strip()) for vtd in sorted(alias_matches)]
    index = load_vtd_bridge_index().get(countyfp) or {}
    candidate_names = {precinct}
    precise_candidate_names = set()
    raw_precinct = re.sub(r'\s+', ' ', precinct).strip()
    exact_name = normalize_bridge_precinct_name(precinct)
    if county in {'BUCKS', 'MONTGOMERY'}:
        raw_parts = [part.strip() for part in re.split(r'\s+X\s+', raw_precinct, flags=re.I) if part.strip()]
        if len(raw_parts) >= 5 and raw_parts[1].upper() == raw_parts[3].upper() and raw_parts[2].upper() == raw_parts[4].upper():
            stem = normalize_bridge_precinct_name(raw_parts[0])
            part_a = normalize_bridge_precinct_name(raw_parts[1])
            part_b = normalize_bridge_precinct_name(raw_parts[2])
            if stem and part_a and part_b:
                precise_candidate_names.add(f'{stem} DISTRICT {part_a} DIVISION {part_b}')
    if county == 'DAUPHIN' and exact_name.startswith('CITY '):
        candidate_names.add(re.sub(r'^CITY\b', 'HARRISBURG', exact_name).strip())
    if county == 'MONROE':
        m = re.match(r'^MIDDLE SMITHFIELD DISTRICT (\d+)$', exact_name)
        if m:
            district_num = int(m.group(1))
            if district_num in (1, 2):
                candidate_names.add('MIDDLE SMITHFIELD DISTRICT EAST')
            if district_num in (3, 4):
                candidate_names.add('MIDDLE SMITHFIELD DISTRICT WEST')
        if exact_name == 'JACKSON':
            candidate_names.add('JACKSON DISTRICT NORTH')
            candidate_names.add('JACKSON DISTRICT SOUTH')
        if exact_name in {'TUNKHANNOCK DISTRICT EAST', 'TUNKHANNOCK DISTRICT WEST'}:
            candidate_names.add('TUNKHANNOCK')
    if county == 'CARBON' and exact_name == 'FRANKLIN DISTRICT FRANKLIN IND DISTRICT FRANKLIN IND':
        candidate_names.add('FRANKLIN DISTRICT FRANKLIN IND')
    if county == 'BUCKS' and exact_name == 'TINICUM DISTRICT TINICM':
        candidate_names.add('TINICUM DISTRICT TINICUM')
    if county == 'LACKAWANNA' and exact_name == 'SPRINGBROOK TOWNSHIP WARD 0 PRECINCT 0':
        candidate_names.add('SPRING BROOK')
    # The Montour 2011 report uses Roman numerals for these two districts.
    # Preserve the source label and expand only this county-specific alias.
    if county == 'MONTOUR' and exact_name in {'MAHONING I', 'MAHONING II'}:
        candidate_names.add('MAHONING DISTRICT ' + {'MAHONING I': '1', 'MAHONING II': '2'}[exact_name])
    if county == 'GREENE' and exact_name == 'MORGAN CHART T GARDEN':
        candidate_names.add('MORGAN DISTRICT CHART T GRDN')
    if county == 'LUZERNE' and exact_name in {'PLYMOUTH', 'PLYMOUTH TOWNSHIP'}:
        candidate_names.add('PLYMOUTH DISTRICT 1')
    if county == 'MONTGOMERY':
        m = re.match(r'^(.*?)\s+DISTRICT\s+(\d+)\s+PRECINCT\s+(\d+)\s+DISTRICT\s+\2\s+PRECINCT\s+\3$', exact_name)
        if m:
            precise_candidate_names.add(f'{m.group(1).strip()} DISTRICT {int(m.group(2))} DIVISION {int(m.group(3))}')
        m = re.match(r'^(.*?)\s+WARD\s+(\d+)\s+PRECINCT\s+(\d+)\s+WARD\s+\2\s+PRECINCT\s+\3$', exact_name)
        if m:
            precise_candidate_names.add(f'{m.group(1).strip()} WARD {int(m.group(2))} PRECINCT {int(m.group(3))}')
            if m.group(1).strip() == 'LOWER MERION' and int(m.group(2)) == 2 and int(m.group(3)) == 2:
                precise_candidate_names.add('LOWER MERION WARD 2')
        m = re.match(r'^(.*?)\s+WARD\s+(\d+)\s+DISTRICT\s+(\d+)$', exact_name)
        if m:
            precise_candidate_names.add(f'{m.group(1).strip()} WARD {int(m.group(2))} DIVISION {int(m.group(3))}')
        m = re.match(r'^(.*?)\s+DISTRICT\s+(\d+)\s+DISTRICT\s+(\d+)$', exact_name)
        if m:
            precise_candidate_names.add(f'{m.group(1).strip()} DISTRICT {int(m.group(2))} DIVISION {int(m.group(3))}')
    candidate_names.update(precise_candidate_names)
    if county == 'NORTHAMPTON':
        m = re.match(r'^(BETHLEHEM WARD \d+)$', exact_name)
        if m:
            candidate_names.add(m.group(1))
        if exact_name == 'LEHIGH DISTRICT PENN':
            candidate_names.add('LEHIGH DISTRICT PENNSVILLE')
        if exact_name == 'ALLEN':
            candidate_names.add('ALLEN DISTRICT NORTH')
            candidate_names.add('ALLEN DISTRICT SOUTH')
        if exact_name == 'LOWER MOUNT BETHEL DISTRICT INDEPENDENT':
            candidate_names.add('LOWER MOUNT BETHEL DISTRICT LOWER')
            candidate_names.add('LOWER MOUNT BETHEL DISTRICT UPPER')
        m = re.match(r'^UPPER MOUNT BETHEL\s+(.+)$', exact_name)
        if m:
            candidate_names.add(f"UPPER MOUNT BETHEL DISTRICT {m.group(1).strip()}")
    def collect_exact(names):
        matches = set()
        for candidate_name in names:
            matches.update(index.get('exact', {}).get(normalize_bridge_precinct_name(candidate_name), set()))
        return matches

    def collect_loose(names):
        matches = set()
        for candidate_name in names:
            for alias in bridge_precinct_aliases(candidate_name):
                matches.update(index.get('loose', {}).get(alias, set()))
        return matches

    exact_matches = collect_exact(precise_candidate_names) if precise_candidate_names else set()
    if len(exact_matches) == 1:
        return [(countyfp, next(iter(exact_matches)))]
    if len(exact_matches) > 1:
        return [(countyfp, vtd) for vtd in sorted(exact_matches)]
    loose_matches = collect_loose(precise_candidate_names) if precise_candidate_names else set()
    if len(loose_matches) == 1:
        return [(countyfp, next(iter(loose_matches)))]
    if len(loose_matches) > 1:
        return [(countyfp, vtd) for vtd in sorted(loose_matches)]

    exact_matches = set()
    for candidate_name in candidate_names:
        exact_matches.update(index.get('exact', {}).get(normalize_bridge_precinct_name(candidate_name), set()))
    if len(exact_matches) == 1:
        return [(countyfp, next(iter(exact_matches)))]
    if len(exact_matches) > 1:
        return [(countyfp, vtd) for vtd in sorted(exact_matches)]
    loose_matches = collect_loose(candidate_names)
    if len(loose_matches) == 1:
        return [(countyfp, next(iter(loose_matches)))]
    if len(loose_matches) > 1:
        return [(countyfp, vtd) for vtd in sorted(loose_matches)]
    return []


def allocate_votes_by_block_counts(votes: int, district_counts):
    if votes <= 0 or not district_counts:
        return {}
    total = sum(float(v or 0) for v in district_counts.values())
    if total <= 0:
        return {}
    raw = {}
    allocated = {}
    for district, count in district_counts.items():
        share = votes * (float(count or 0) / total)
        raw[district] = share
        allocated[district] = int(share)
    remainder = votes - sum(allocated.values())
    if remainder > 0:
        order = sorted(raw.keys(), key=lambda district: (raw[district] - allocated[district], int(district)), reverse=True)
        for district in order[:remainder]:
            allocated[district] += 1
    return {district: amount for district, amount in allocated.items() if amount > 0}


def add_result_votes(node, votes: int, party: str, candidate: str):
    if votes <= 0:
        return
    if party in PARTY_DEM or party == 'YES':
        node['dem_votes'] += votes
        node['dem_candidate'] = merge_candidate_label(node.get('dem_candidate'), candidate)
    elif party in PARTY_REP or party == 'NO':
        node['rep_votes'] += votes
        node['rep_candidate'] = merge_candidate_label(node.get('rep_candidate'), candidate)
    else:
        node['other_votes'] += votes
    node['total_votes'] += votes


def merge_candidate_label(existing, candidate):
    existing = normalize_candidate_label(existing)
    candidate = normalize_candidate_label(candidate)
    if not candidate:
        return existing
    names = []
    # Some official exports express a joint ticket with the same delimiter we
    # use for multiple candidates.  Tokenize both values before de-duplicating;
    # comparing the complete joint-ticket string to its individual components
    # caused the ticket to be appended once for every precinct row.
    for value in (existing, candidate):
        for part in value.split(' / '):
            part = part.strip()
            if part and part not in names:
                names.append(part)
    return ' / '.join(names)


def normalize_candidate_label(value):
    """Normalize exported candidate labels without altering candidate identity."""
    value = re.sub(r'\s+', ' ', (value or '').strip())
    if not value:
        return ''

    # Keep the public-facing presidential label stable across official files,
    # which variously use the full middle name, middle initial, or no middle
    # name for the same candidate.
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() in {
        'donald john trump', 'donald j trump', 'donald trump'
    }:
        return 'Donald J. Trump'
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() in {
        'joseph robinette biden jr', 'joseph r biden jr',
        'joseph biden jr', 'joe biden'
    }:
        return 'Joe Biden'
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() in {
        'douglas v mastriano', 'doug mastriano'
    }:
        return 'Doug Mastriano'
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() in {
        'robert p casey jr', 'bob casey jr', 'jr bob casey'
    }:
        return 'Bob Casey, Jr.'
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() in {
        'david h mccormick', 'dave mccormick'
    }:
        return 'David H. McCormick'
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() == 'eugene depasquale':
        return 'Eugene DePasquale'
    if re.sub(r'[^a-z0-9]+', ' ', value.lower()).strip() in {
        'timothy l defoor', 'timothy lionel defoor', 'timothy defoor', 'tim defoor'
    }:
        return 'Tim DeFoor'

    def format_name(name):
        words = []
        for raw_word in re.split(r'\s+', name.strip()):
            bare = raw_word.rstrip('.')
            upper = bare.upper()
            if not bare:
                continue
            if upper in {'JR', 'SR'}:
                words.append(f'{upper.title()}.')
            elif upper in {'II', 'III', 'IV', 'V', 'VI'}:
                words.append(upper)
            elif len(bare) == 1 and bare.isalpha():
                words.append(f'{bare.upper()}.')
            else:
                parts = []
                for part in raw_word.split('-'):
                    titled = part[:1].upper() + part[1:].lower()
                    if len(titled) > 3 and titled.lower().startswith('mc'):
                        titled = 'Mc' + titled[2:3].upper() + titled[3:]
                    parts.append(titled)
                words.append('-'.join(parts))
        return ' '.join(words)

    retention = re.match(r'^(Yes|No)\s+(?:—|�|\x96)\s+(.+)$', value, re.I)
    if retention:
        return f'{retention.group(1).title()} — {format_name(retention.group(2))}'
    return ' / '.join(format_name(part) for part in value.split('/') if part.strip())


def finalize_result_node(node):
    total = int(node.get('total_votes') or 0)
    dem = int(node.get('dem_votes') or 0)
    rep = int(node.get('rep_votes') or 0)
    other = max(total - dem - rep, 0)
    node['other_votes'] = other
    node['total_votes'] = total
    if total > 0:
        if rep > dem:
            winner = 'R'
            margin = rep - dem
        elif dem > rep:
            winner = 'D'
            margin = dem - rep
        else:
            winner = 'T'
            margin = 0
        node['winner'] = winner
        node['margin'] = float(margin)
        node['margin_pct'] = float((abs(rep - dem) / total) * 100)
    else:
        node['winner'] = ''
        node['margin'] = 0
        node['margin_pct'] = 0


def dra_scope_contest_year_from_filename(path: Path):
    match = DRA_DISTRICT_STATS_FILENAME.match(path.name)
    if not match:
        return None
    scope_label = re.sub(r'\s+', ' ', (match.group(1) or '').strip().lower())
    scope = DRA_SCOPE_LABEL_TO_SCOPE.get(scope_label)
    year = safe_int(match.group(2))
    contest_raw = (match.group(3) or '').strip().lower()
    contest_token = re.sub(r'[^a-z0-9]+', '', contest_raw)
    contest_type = DRA_CONTEST_TOKEN_TO_CONTEST.get(contest_token)
    if not scope or not contest_type or year <= 0:
        return None
    return scope, contest_type, year


def load_dra_district_share_inputs():
    shares_by_key = {}
    source_file_by_key = {}
    for fp in sorted(data_dir.glob('district-statistics *.csv')):
        parsed = dra_scope_contest_year_from_filename(fp)
        if not parsed:
            continue
        scope, contest_type, year = parsed
        key = (scope, contest_type, year)
        rows = {}
        try:
            with fp.open('r', encoding='utf-8-sig', newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    district_id = normalize_district_id(row.get('ID') or row.get('District') or '')
                    if not district_id:
                        continue
                    district_num = int(district_id)
                    max_district = CURRENT_SCOPE_DISTRICT_MAX.get(scope, 0)
                    if district_num <= 0 or (max_district and district_num > max_district):
                        continue
                    shares = normalized_vote_shares(row.get('Dem'), row.get('Rep'), row.get('Oth'))
                    if not shares:
                        continue
                    rows[district_id] = {
                        'dem_share': shares[0],
                        'rep_share': shares[1],
                        'other_share': shares[2],
                    }
        except Exception:
            continue
        if rows:
            shares_by_key[key] = rows
            source_file_by_key[key] = fp.name
    return shares_by_key, source_file_by_key


def apply_dra_share_calibration(district_nodes, source_by_key):
    dra_shares, dra_sources = load_dra_district_share_inputs()
    for key, district_shares in dra_shares.items():
        contest = district_nodes.get(key)
        if not contest:
            continue
        totals = [int((node or {}).get('total_votes') or 0) for node in contest.values()]
        fallback_total = int(round(sum(totals) / max(len(totals), 1))) if totals else 0
        if fallback_total <= 0:
            fallback_total = 1000

        dem_candidates = defaultdict(int)
        rep_candidates = defaultdict(int)
        for node in contest.values():
            dem_candidate = (node.get('dem_candidate') or '').strip()
            rep_candidate = (node.get('rep_candidate') or '').strip()
            if dem_candidate:
                dem_candidates[dem_candidate] += 1
            if rep_candidate:
                rep_candidates[rep_candidate] += 1
        default_dem_candidate = max(dem_candidates.items(), key=lambda item: item[1])[0] if dem_candidates else ''
        default_rep_candidate = max(rep_candidates.items(), key=lambda item: item[1])[0] if rep_candidates else ''

        for district_id, shares in district_shares.items():
            node = contest.get(district_id)
            base_total = int((node or {}).get('total_votes') or 0)
            if base_total <= 0:
                base_total = fallback_total
            allocation = allocate_votes_by_shares(
                base_total,
                shares.get('dem_share'),
                shares.get('rep_share'),
                shares.get('other_share'),
            )
            if not allocation:
                continue
            if node is None:
                node = {
                    'dem_votes': 0,
                    'rep_votes': 0,
                    'other_votes': 0,
                    'total_votes': 0,
                    'dem_candidate': default_dem_candidate,
                    'rep_candidate': default_rep_candidate,
                }
                contest[district_id] = node
            node['dem_votes'] = int(allocation['dem_votes'])
            node['rep_votes'] = int(allocation['rep_votes'])
            node['other_votes'] = int(allocation['other_votes'])
            node['total_votes'] = int(node['dem_votes'] + node['rep_votes'] + node['other_votes'])
            if default_dem_candidate and not node.get('dem_candidate'):
                node['dem_candidate'] = default_dem_candidate
            if default_rep_candidate and not node.get('rep_candidate'):
                node['rep_candidate'] = default_rep_candidate
        source_file = dra_sources.get(key) or ''
        source_by_key[key] = f'dra_district_statistics_share_calibration/{source_file}'


def aggregate_county_results_from_openelections():
    results_by_year = defaultdict(dict)

    for year, fp in iter_openelections_csvs():
        try:
            rows = read_csv_rows(fp)
        except Exception:
            continue
        partisan_courts = {
            office_mapping_for_contest(r.get('office') or '')
            for r in rows
            if (r.get('party') or '').strip().upper() in PARTY_DEM | PARTY_REP
        }

        for r in rows:
            county = (r.get('county') or '').strip()
            office = (r.get('office') or '').strip()
            if not county or not office:
                continue

            office_key = office_mapping_for_contest(office)
            if not is_statewide_contest_type(office_key):
                continue
            if ' retention - ' in office.lower() and office_key in partisan_courts:
                continue

            party = (r.get('party') or '').strip().upper()
            candidate = (r.get('candidate') or '').strip()
            if ' retention - ' in office.lower():
                justice = office.split(' - ', 1)[1].strip()
                candidate = f'{candidate} — {justice}'
            # Normalized historical files can contain fractional precinct rows
            # created by crosswalk disaggregation.  Truncating each row here
            # systematically loses votes in nearly every county.  Preserve the
            # fractions until the county/contest node is complete, then round
            # once with largest remainder below.
            votes = safe_float(r.get('votes'))
            if votes <= 0:
                continue

            year_bucket = results_by_year[year]
            office_bucket = year_bucket.setdefault(office_key, {})
            contest = office_bucket.setdefault('statewide', {'results': {}})
            county_bucket = contest['results']
            cnode = county_bucket.setdefault(county.upper(), {
                'dem_votes': 0,
                'rep_votes': 0,
                'other_votes': 0,
                'total_votes': 0,
                'dem_candidate': '',
                'rep_candidate': '',
            })

            if party in PARTY_DEM or party == 'YES':
                cnode['dem_votes'] += votes
                cnode['dem_candidate'] = merge_candidate_label(cnode.get('dem_candidate'), candidate)
            elif party in PARTY_REP or party == 'NO':
                cnode['rep_votes'] += votes
                cnode['rep_candidate'] = merge_candidate_label(cnode.get('rep_candidate'), candidate)
            else:
                cnode['other_votes'] += votes
            cnode['total_votes'] += votes

    for year, office_bucket in results_by_year.items():
        for office_key, contests in office_bucket.items():
            for contest_key, contest_obj in contests.items():
                for cname, v in contest_obj['results'].items():
                    rounded, target_total = round_fractional_vote_components(v)
                    v.update(rounded)
                    v['total_votes'] = target_total
                    finalize_result_node(v)
    return {'results_by_year': results_by_year}


def build_election_aggregated(out_path: Path, county_names=None):
    payload = aggregate_county_results_from_openelections()
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)
    return payload


# ------------------------------------------------------------
# 4) Build actual district contest files plus a disabled fallback payload
# ------------------------------------------------------------
def build_district_results_2022_lines(out_path: Path):
    payload = {
        'meta': {
            'generated_for': 'pa_precinct_map_actual',
            'scope': 'district_fallback_disabled',
            'description': 'Synthetic district fallback disabled. Use real district slice files or statewide county contest results.'
        },
        'results_by_year': {},
    }
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)


def build_district_manifests(contest_dir: Path, contest_types=None, years=None):
    contest_dir.mkdir(parents=True, exist_ok=True)
    contest_types = set(contest_types or [])
    years = {int(year) for year in (years or [])}
    target_years = {
        'us_house': {2022, 2024},
        'state_house': {2022, 2024},
        'state_senate': {2024},
    }
    district_nodes = {}
    source_by_key = {}
    files = []
    manifest_path = contest_dir / 'manifest.json'
    if contest_types and manifest_path.exists():
        try:
            existing_manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            files = [
                entry for entry in (existing_manifest.get('files') or [])
                if entry.get('contest_type') not in contest_types
            ]
        except (OSError, json.JSONDecodeError):
            files = []
    source_rows = []
    vtd_match_cache = {}
    allocation_audit = defaultdict(lambda: {
        'source_rows': 0,
        'source_votes': 0,
        'matched_rows': 0,
        'matched_votes': 0,
        'unmatched_rows': 0,
        'unmatched_votes': 0,
        'unmatched_precincts': set(),
        'unmatched_precinct_votes': Counter(),
        'mapping_methods': Counter(),
        'scopes': defaultdict(lambda: {
            'allocated_rows': 0,
            'allocated_votes': 0,
            'unallocated_rows': 0,
            'unallocated_votes': 0,
        }),
    })

    if OFFICIAL_2020_STATEWIDE_SOURCE.exists():
        source_rows.append((2020, OFFICIAL_2020_STATEWIDE_SOURCE, 'official_pa_precinct_export'))
    if OFFICIAL_2024_DISTRICT_SOURCE.exists():
        source_rows.append((2024, OFFICIAL_2024_DISTRICT_SOURCE, 'official_pa_precinct_export'))
    for year, fp in iter_openelections_csvs():
        if year == 2020 and OFFICIAL_2020_STATEWIDE_SOURCE.exists():
            continue
        if year == 2024 and OFFICIAL_2024_DISTRICT_SOURCE.exists():
            continue
        source_rows.append((year, fp, 'openelections_precinct_aggregate'))

    for year, fp, source_label in source_rows:
        if years and year not in years:
            continue
        try:
            rows = read_csv_rows(fp)
        except Exception:
            continue
        rows = apply_official_county_party_controls(rows, year, contest_types=contest_types)

        partisan_courts = {
            office_mapping_for_contest(r.get('office') or '')
            for r in rows
            if (r.get('party') or '').strip().upper() in PARTY_DEM | PARTY_REP
        }

        for row in rows:
            office_key = office_mapping_for_contest(row.get('office') or '')
            if contest_types and office_key not in contest_types:
                continue
            if ' retention - ' in (row.get('office') or '').lower() and office_key in partisan_courts:
                continue
            votes = safe_int(row.get('votes'))
            if votes <= 0:
                continue
            party = (row.get('party') or '').strip().upper()
            candidate = (row.get('candidate') or '').strip()
            office = (row.get('office') or '').strip()
            if ' retention - ' in office.lower():
                justice = office.split(' - ', 1)[1].strip()
                candidate = f'{candidate} — {justice}'

            if office_key in target_years and year in target_years[office_key]:
                district_id = normalize_district_id(row.get('district') or '')
                if district_id:
                    scope = DISTRICT_SCOPE_BY_CONTEST[office_key]
                    key = (scope, office_key, year)
                    source_by_key.setdefault(key, source_label)
                    contest = district_nodes.setdefault(key, {})
                    node = contest.setdefault(district_id, {
                        'dem_votes': 0,
                        'rep_votes': 0,
                        'other_votes': 0,
                        'total_votes': 0,
                        'dem_candidate': '',
                        'rep_candidate': '',
                    })
                    add_result_votes(node, votes, party, candidate)

            if is_statewide_contest_type(office_key):
                audit_key = (office_key, year)
                audit = allocation_audit[audit_key]
                audit['source_rows'] += 1
                audit['source_votes'] += votes
                match_key = (
                    normalize_county_name(row.get('county') or ''),
                    normalize_bridge_precinct_name(row.get('precinct') or '')
                )
                countyfp = county_fips_by_name().get(match_key[0]) or ''
                block_maps = load_vtd_current_district_blocks()
                maintained_targets = maintained_targets_for_row(row, year, countyfp) if countyfp else []
                if maintained_targets:
                    maintained_targets = [
                        target for target in maintained_targets
                        if any(block_maps.get(scope, {}).get((target[0], target[1])) for scope in block_maps)
                    ]
                if maintained_targets:
                    weighted_vtds = [(county, vtd, weight) for county, vtd, weight, _method in maintained_targets]
                    for _county, _vtd, _weight, method in maintained_targets:
                        audit['mapping_methods'][method] += 1
                else:
                    if match_key not in vtd_match_cache:
                        vtd_match_cache[match_key] = match_row_to_current_vtds(row)
                    weighted_vtds = [(*vtd_key, 1.0) for vtd_key in (vtd_match_cache.get(match_key) or [])]
                    weighted_vtds = [
                        target for target in weighted_vtds
                        if any(block_maps.get(scope, {}).get((target[0], target[1])) for scope in block_maps)
                    ]
                    if weighted_vtds:
                        audit['mapping_methods']['current_precinct_or_vtd_name'] += 1
                if not weighted_vtds:
                    audit['unmatched_rows'] += 1
                    audit['unmatched_votes'] += votes
                    unmatched_key = '|'.join(match_key)
                    audit['unmatched_precincts'].add(unmatched_key)
                    audit['unmatched_precinct_votes'][unmatched_key] += votes
                    continue
                audit['matched_rows'] += 1
                audit['matched_votes'] += votes
                for scope in ('congressional', 'state_house', 'state_senate'):
                    direct_district_id = ''
                    if scope == 'congressional' and year == 2024 and source_label == 'official_pa_precinct_export':
                        direct_district_id = embedded_congressional_district_from_precinct_label(row.get('precinct') or '')
                    if direct_district_id:
                        allocations = {direct_district_id: votes}
                    else:
                        district_counts = defaultdict(int)
                        for target_county, target_vtd, target_weight in weighted_vtds:
                            vtd_key = (target_county, target_vtd)
                            for district_id, block_count in (block_maps.get(scope, {}).get(vtd_key) or {}).items():
                                district_counts[district_id] += float(block_count or 0) * float(target_weight or 0)
                        allocations = allocate_votes_by_block_counts(votes, district_counts)
                    if not allocations:
                        audit['scopes'][scope]['unallocated_rows'] += 1
                        audit['scopes'][scope]['unallocated_votes'] += votes
                        continue
                    allocated_votes = sum(int(value or 0) for value in allocations.values())
                    if allocated_votes != votes:
                        raise RuntimeError(
                            f'Vote conservation failed for {year} {office_key} {match_key} '
                            f'in {scope}: source={votes}, allocated={allocated_votes}'
                        )
                    audit['scopes'][scope]['allocated_rows'] += 1
                    audit['scopes'][scope]['allocated_votes'] += allocated_votes
                    key = (scope, office_key, year)
                    source_by_key.setdefault(key, f'{source_label}_to_current_lines_via_vtd_block_assign')
                    contest = district_nodes.setdefault(key, {})
                    for district_id, district_votes in allocations.items():
                        node = contest.setdefault(district_id, {
                            'dem_votes': 0,
                            'rep_votes': 0,
                            'other_votes': 0,
                            'total_votes': 0,
                            'dem_candidate': '',
                            'rep_candidate': '',
                        })
                        add_result_votes(node, district_votes, party, candidate)

    apply_dra_share_calibration(district_nodes, source_by_key)

    allowed_incremental_contests = None
    if contest_types:
        try:
            county_manifest = json.loads((data_dir / 'contests' / 'manifest.json').read_text(encoding='utf-8'))
            allowed_incremental_contests = {
                (entry.get('contest_type'), int(entry.get('year')))
                for entry in (county_manifest.get('files') or [])
            }
        except (OSError, ValueError, TypeError):
            allowed_incremental_contests = None

    for (scope, contest_type, year), results in sorted(district_nodes.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])):
        if allowed_incremental_contests is not None and (contest_type, int(year)) not in allowed_incremental_contests:
            continue
        finalized = {}
        for district_id, node in sorted(results.items(), key=lambda item: int(item[0])):
            finalize_result_node(node)
            finalized[district_id] = node
        if not finalized:
            continue
        fname = f'{scope}_{contest_type}_{year}.json'
        expected = expected_district_count(scope, contest_type, year)
        audit = allocation_audit.get((contest_type, year)) or {}
        scope_audit = (audit.get('scopes') or {}).get(scope, {})
        source_votes = int(audit.get('source_votes') or 0)
        allocated_votes = int(scope_audit.get('allocated_votes') or 0)
        payload = {
            'scope': scope,
            'contest_type': contest_type,
            'year': year,
            'meta': {
                'districts_observed': len(finalized),
                'districts_expected': expected,
                'coverage_percent': round((len(finalized) / max(expected, 1)) * 100, 2),
                'source': source_by_key.get((scope, contest_type, year), 'openelections_precinct_aggregate'),
                'allocation_audit': {
                    'source_rows': int(audit.get('source_rows') or 0),
                    'source_votes': source_votes,
                    'matched_rows': int(audit.get('matched_rows') or 0),
                    'matched_votes': int(audit.get('matched_votes') or 0),
                    'unmatched_rows': int(audit.get('unmatched_rows') or 0),
                    'unmatched_votes': int(audit.get('unmatched_votes') or 0),
                    'unmatched_precincts': sorted(audit.get('unmatched_precincts') or []),
                    'unmatched_precinct_votes': dict(sorted(
                        (audit.get('unmatched_precinct_votes') or {}).items()
                    )),
                    'mapping_methods': dict(sorted((audit.get('mapping_methods') or {}).items())),
                    'allocated_rows': int(scope_audit.get('allocated_rows') or 0),
                    'allocated_votes': allocated_votes,
                    'unallocated_rows': int(scope_audit.get('unallocated_rows') or 0),
                    'unallocated_votes': int(scope_audit.get('unallocated_votes') or 0),
                    'allocation_vote_delta': allocated_votes - source_votes,
                    'conserved_for_matched_rows': (
                        allocated_votes == int(audit.get('matched_votes') or 0)
                        and not int(scope_audit.get('unallocated_votes') or 0)
                    ),
                },
            },
            'general': {'results': finalized}
        }
        with (contest_dir / fname).open('w', encoding='utf-8') as f:
            json.dump(payload, f, indent=2)
        files.append({'scope': scope, 'contest_type': contest_type, 'year': year, 'file': fname, 'districts': expected, 'rows': len(finalized)})

    manifest = {'scope': 'multi', 'files': files}
    with (contest_dir / 'manifest.json').open('w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)


def build_contest_manifests(contest_dir: Path, aggregated_payload=None):
    aggregated_payload = aggregated_payload or aggregate_county_results_from_openelections()
    results_by_year = aggregated_payload.get('results_by_year', {})
    files = []
    for year in sorted(results_by_year.keys(), key=int):
        year_bucket = results_by_year.get(year, {})
        for contest_type in sorted(year_bucket):
            if not is_statewide_contest_type(contest_type):
                continue
            contest = year_bucket.get(contest_type, {}).get('statewide') or {}
            contest_results = contest.get('results') or {}
            if not contest_results:
                continue
            if contest_type in {'supreme_court', 'superior_court', 'commonwealth_court'} and len(contest_results) < 67:
                # Several legacy official precinct exports contain court rows
                # with literal zero vote totals for whole counties. Do not
                # advertise a visibly incomplete statewide contest.
                continue
            fname = f'{contest_type}_{year}.json'
            rows = []
            for county in sorted(contest_results.keys()):
                node = contest_results[county]
                rows.append({
                    'county': county,
                    'dem_votes': int(node.get('dem_votes') or 0),
                    'rep_votes': int(node.get('rep_votes') or 0),
                    'other_votes': int(node.get('other_votes') or 0),
                    'total_votes': int(node.get('total_votes') or 0),
                    'dem_candidate': node.get('dem_candidate') or '',
                    'rep_candidate': node.get('rep_candidate') or '',
                    'margin': float(node.get('margin') or 0),
                    'margin_pct': float(node.get('margin_pct') or 0),
                    'winner': node.get('winner') or '',
                    'color': '#2563eb' if (node.get('winner') == 'D') else '#dc2626' if (node.get('winner') == 'R') else '#6b7280'
                })
            payload = {'contest': contest_type, 'year': year, 'rows': []}
            payload['rows'] = rows
            with (contest_dir / fname).open('w', encoding='utf-8') as f:
                json.dump(payload, f, indent=2)
            files.append({'contest_type': contest_type, 'year': int(year), 'file': fname, 'rows': len(rows)})

    with (contest_dir / 'manifest.json').open('w', encoding='utf-8') as f:
        json.dump({'files': files}, f, indent=2)


# ------------------------------------------------------------
# 5) Build district GeoJSON overlays from TIGER shapefiles with a placeholder fallback
# ------------------------------------------------------------

def feature_collection_with_props(features, id_field):
    return {
        'type': 'FeatureCollection',
        'features': [
            {
                'type': 'Feature',
                'properties': {'id': str(i), id_field: str(i)},
                'geometry': {
                    'type': 'Polygon',
                    'coordinates': [[
                        [-80.6 + (i * 0.03), 39.72],
                        [-80.57 + (i * 0.03), 39.72],
                        [-80.57 + (i * 0.03), 39.76],
                        [-80.6 + (i * 0.03), 39.76],
                        [-80.6 + (i * 0.03), 39.72]
                    ]]
                }
            }
            for i in features
        ]
    }


def normalize_district_prop(value):
    text = str(value or '').strip()
    digits = re.sub(r'[^0-9]', '', text)
    if digits:
        return str(int(digits))
    return text


def build_district_tileset_from_zip(zip_path: Path, output_path: Path, source_field: str, output_field: str, fallback_range):
    if gpd is None or not zip_path.exists():
        output_path.write_text(json.dumps(feature_collection_with_props(fallback_range, output_field)))
        return
    try:
        gdf = gpd.read_file(f'zip://{zip_path.resolve()}')
        if gdf.crs and str(gdf.crs) != 'EPSG:4326':
            gdf = gdf.to_crs(epsg=4326)
        keep = gdf[[source_field, 'geometry']].copy()
        keep[source_field] = keep[source_field].apply(normalize_district_prop)
        keep[output_field] = keep[source_field]
        keep['id'] = keep[output_field]
        cols = ['id']
        if output_field not in cols:
            cols.append(output_field)
        if source_field not in cols:
            cols.append(source_field)
        cols.append('geometry')
        features = json.loads(keep[cols].to_json())
        output_path.write_text(json.dumps(features))
    except Exception:
        output_path.write_text(json.dumps(feature_collection_with_props(fallback_range, output_field)))


def build_district_tilesets():
    build_district_tileset_from_zip(
        data_dir / 'tl_2022_42_cd118.zip',
        data_dir / 'tileset' / 'pa_cd118_tileset.geojson',
        'CD118FP',
        'DISTRICT',
        range(1, 18)
    )
    build_district_tileset_from_zip(
        data_dir / 'tl_2022_42_sldl.zip',
        data_dir / 'tileset' / 'pa_state_house_2022_lines_tileset.geojson',
        'SLDLST',
        'SLDLST',
        range(1, 204)
    )
    build_district_tileset_from_zip(
        data_dir / 'tl_2022_42_sldu.zip',
        data_dir / 'tileset' / 'pa_state_senate_2022_lines_tileset.geojson',
        'SLDUST',
        'SLDUST',
        range(1, 51)
    )


if __name__ == '__main__':
    # copy existing county boundary if exists
    src_county = base / 'data' / 'pa_counties.geojson'
    dst_county = data_dir / 'pa_counties.geojson'
    county_names = []
    if src_county.exists() and not dst_county.exists():
        dst_county.write_bytes(src_county.read_bytes())
    county_names = county_names_from_data_geojson(dst_county if dst_county.exists() else src_county)

    build_pa_congressional_districts(data_dir / 'pa_congressional_districts.csv')
    build_state_house_csv(data_dir / 'pa_state_house_districts.csv')
    build_state_senate_csv(data_dir / 'pa_state_senate_districts.csv')
    build_district_descriptions(data_dir / 'pa_district_descriptions.json')

    if dst_county.exists():
        build_county_demographics(dst_county, data_dir / 'county_demographics_2020_dp1.json')

    aggregated_payload = build_election_aggregated(data_dir / 'pa_elections_aggregated.json', county_names=county_names)
    build_district_results_2022_lines(data_dir / 'pa_district_results_2022_lines.json')
    build_district_manifests(data_dir / 'district_contests')
    build_contest_manifests(data_dir / 'contests', aggregated_payload=aggregated_payload)

    build_district_tilesets()
    vtd_block_counts = load_vtd_block_counts_from_blockassign(
        base / 'data' / 'BlockAssign_ST42_PA.zip',
        'BlockAssign_ST42_PA_VTD.txt'
    )
    build_vtd_block_counts_report(data_dir / 'vtd_block_counts.csv', vtd_block_counts)
    build_vtd_precinct_and_centroid_layers(
        base / 'Data' / 'tl_2020_42_vtd20.zip',
        load_county_lookup_from_geojson(src_county),
        data_dir / 'Voting_Precincts.geojson',
        data_dir / 'precinct_centroids.geojson',
        block_counts_by_vtd=vtd_block_counts
    )

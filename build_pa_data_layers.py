import csv, json
from pathlib import Path
import re
import zipfile
from collections import defaultdict
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
    for d in range(1, 19):
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
        'congressional': {str(i): f'PA Congressional District {i}' for i in range(1, 19)},
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
    geodf['precinct_name'] = geodf['VTD']
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
DATA_ROOT = base / 'Data' / 'Openelections'

PARTY_DEM = {'DEM', 'D'}
PARTY_REP = {'REP', 'R'}
STATEWIDE_CONTEST_TYPES = ['president', 'governor', 'us_senate', 'attorney_general', 'secretary_of_state', 'treasurer', 'auditor']
DISTRICT_SCOPE_BY_CONTEST = {
    'us_house': 'congressional',
    'state_house': 'state_house',
    'state_senate': 'state_senate',
}
EXPECTED_DISTRICT_COUNT = {
    'congressional': 18,
    'state_house': 203,
    'state_senate': 50,
}
OFFICIAL_2024_STATEWIDE_OE_SOURCE = DATA_ROOT / '2024' / '20241105__pa__general__precinct_official.csv'
OFFICIAL_2024_DISTRICT_SOURCE = base / 'Data' / 'erstat_2024_g_268768_20250129.txt'
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
}
RAW_COUNTY_NAME_BY_FIPS = None


def iter_openelections_csvs():
    years = sorted([int(p.name) for p in DATA_ROOT.iterdir() if p.is_dir() and p.name.isdigit() and 2000 <= int(p.name) <= 2024])
    for y in years:
        year_dir = DATA_ROOT / str(y)
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


def read_csv_rows(path: Path):
    with path.open('r', encoding='utf-8-sig', errors='ignore') as f:
        text = f.read()
    rows = []
    lines = text.splitlines()
    if not lines:
        return rows
    first = [p.strip().strip('"') for p in lines[0].split(',')]
    if first and first[0].isdigit() and (len(first) < 2 or first[1].upper() in {'G', 'P', 'S'}):
        return read_raw_precinct_rows(lines)
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
    return rows


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
        if len(raw) >= 37 and str(raw[29]).isdigit():
            county_fips = str(raw[29]).zfill(3)
        elif len(raw) >= 28 and str(raw[27]).isdigit():
            county_fips = str(raw[27]).zfill(3)
        county = county_lookup.get(county_fips, county_fips)
        name_start = 22 if len(raw) >= 35 else 20
        precinct = ' '.join(part for part in raw[name_start:name_start + 5] if part).strip()
        district = ''
        if office_code == 'USC':
            district = raw[18].strip() if len(raw) >= 37 else raw[16].strip()
        elif office_code == 'STS':
            district = raw[19].strip() if len(raw) >= 37 else raw[17].strip()
        elif office_code == 'STH':
            district = raw[20].strip() if len(raw) >= 37 else raw[18].strip()
        candidate = ' '.join(part for part in [raw[12], raw[13], raw[11], raw[14]] if part).strip().title() or 'Write Ins'
        rows.append({
            'county': county,
            'precinct': precinct,
            'office': office,
            'district': district,
            'party': (raw[9] or '').strip(),
            'candidate': candidate,
            'votes': (raw[15] or '').strip(),
        })
    return rows


def office_mapping_for_contest(office: str):
    o = re.sub(r'\s+', ' ', (office or '').strip().lower())
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
    return None


def safe_int(value):
    try:
        return int(float((value or 0)))
    except Exception:
        return 0


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
        if int(year) >= 2022:
            return 17
        return EXPECTED_DISTRICT_COUNT[scope]
    if scope == 'state_senate' and contest_type == 'state_senate':
        return 25
    return EXPECTED_DISTRICT_COUNT.get(scope, 0)


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


def aggregate_county_results_from_openelections():
    results_by_year = defaultdict(dict)

    for year, fp in iter_openelections_csvs():
        try:
            rows = read_csv_rows(fp)
        except Exception:
            continue

        for r in rows:
            county = (r.get('county') or '').strip()
            office = (r.get('office') or '').strip()
            if not county or not office:
                continue

            office_key = office_mapping_for_contest(office)
            if office_key not in STATEWIDE_CONTEST_TYPES:
                continue

            party = (r.get('party') or '').strip().upper()
            candidate = (r.get('candidate') or '').strip()
            votes = safe_int(r.get('votes'))
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

            if party in PARTY_DEM:
                cnode['dem_votes'] += votes
                if candidate and not cnode['dem_candidate']:
                    cnode['dem_candidate'] = candidate
            elif party in PARTY_REP:
                cnode['rep_votes'] += votes
                if candidate and not cnode['rep_candidate']:
                    cnode['rep_candidate'] = candidate
            else:
                cnode['other_votes'] += votes
            cnode['total_votes'] += votes

    for year, office_bucket in results_by_year.items():
        for office_key, contests in office_bucket.items():
            for contest_key, contest_obj in contests.items():
                for cname, v in contest_obj['results'].items():
                    finalize_result_node(v)
    return {'results_by_year': results_by_year}


def build_election_aggregated(out_path: Path, county_names=None):
    payload = aggregate_county_results_from_openelections()
    with out_path.open('w', encoding='utf-8') as f:
        json.dump(payload, f)
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


def build_district_manifests(contest_dir: Path):
    target_years = {
        'us_house': {2022, 2024},
        'state_house': {2022, 2024},
        'state_senate': {2024},
    }
    district_nodes = {}
    source_by_key = {}
    files = []
    source_rows = []

    if OFFICIAL_2024_DISTRICT_SOURCE.exists():
        source_rows.append((2024, OFFICIAL_2024_DISTRICT_SOURCE, 'official_pa_precinct_export'))
    for year, fp in iter_openelections_csvs():
        if year == 2024 and OFFICIAL_2024_DISTRICT_SOURCE.exists():
            continue
        source_rows.append((year, fp, 'openelections_precinct_aggregate'))

    for year, fp, source_label in source_rows:
        try:
            rows = read_csv_rows(fp)
        except Exception:
            continue

        for row in rows:
            office_key = office_mapping_for_contest(row.get('office') or '')
            if office_key not in target_years or year not in target_years[office_key]:
                continue
            district_id = normalize_district_id(row.get('district') or '')
            if not district_id:
                continue
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
            votes = safe_int(row.get('votes'))
            if votes <= 0:
                continue
            party = (row.get('party') or '').strip().upper()
            candidate = (row.get('candidate') or '').strip()
            if party in PARTY_DEM:
                node['dem_votes'] += votes
                if candidate and not node['dem_candidate']:
                    node['dem_candidate'] = candidate
            elif party in PARTY_REP:
                node['rep_votes'] += votes
                if candidate and not node['rep_candidate']:
                    node['rep_candidate'] = candidate
            else:
                node['other_votes'] += votes
            node['total_votes'] += votes

    for (scope, contest_type, year), results in sorted(district_nodes.items(), key=lambda item: (item[0][0], item[0][2], item[0][1])):
        finalized = {}
        for district_id, node in results.items():
            finalize_result_node(node)
            finalized[district_id] = node
        if not finalized:
            continue
        fname = f'{scope}_{contest_type}_{year}.json'
        expected = expected_district_count(scope, contest_type, year)
        payload = {
            'scope': scope,
            'contest_type': contest_type,
            'year': year,
            'meta': {
                'districts_observed': len(finalized),
                'districts_expected': expected,
                'coverage_percent': round((len(finalized) / max(expected, 1)) * 100, 2),
                'source': source_by_key.get((scope, contest_type, year), 'openelections_precinct_aggregate'),
            },
            'general': {'results': finalized}
        }
        with (contest_dir / fname).open('w', encoding='utf-8') as f:
            json.dump(payload, f)
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
        for contest_type in STATEWIDE_CONTEST_TYPES:
            contest = year_bucket.get(contest_type, {}).get('statewide') or {}
            contest_results = contest.get('results') or {}
            if not contest_results:
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
                json.dump(payload, f)
            files.append({'contest_type': contest_type, 'year': int(year), 'file': fname, 'rows': len(rows)})

    with (contest_dir / 'manifest.json').open('w', encoding='utf-8') as f:
        json.dump({'files': files}, f, indent=2)


# ------------------------------------------------------------
# 5) Create geojson placeholders for districts if source shapes aren't available
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
                        [i * 0.1, 39.7], [i * 0.1 + 0.08, 39.7], [i * 0.1 + 0.08, 39.78], [i * 0.1, 39.78], [i * 0.1, 39.7]
                    ]]
                }
            }
            for i in features
        ]
    }


def build_tileset_placeholders():
    # keep a tiny but valid set to avoid missing-layer failures for each district scale.
    # IDs should include known prop names in map: DISTRICT, SLDLST, SLDUST
    cd_path = data_dir / 'tileset' / 'pa_cd118_tileset.geojson'
    if not cd_path.exists():
        cd_path.write_text(json.dumps(feature_collection_with_props(range(1, 19), 'DISTRICT')))

    sh_path = data_dir / 'tileset' / 'pa_state_house_2022_lines_tileset.geojson'
    if not sh_path.exists():
        sh_path.write_text(json.dumps(feature_collection_with_props(range(1, 204), 'SLDLST')))

    ss_path = data_dir / 'tileset' / 'pa_state_senate_2022_lines_tileset.geojson'
    if not ss_path.exists():
        ss_path.write_text(json.dumps(feature_collection_with_props(range(1, 51), 'SLDUST')))

# ------------------------------------------------------------
def build_state_senate_tileset(path: Path):
    path.write_text(json.dumps(feature_collection_with_props(range(1, 51), 'SLDUST')))


if __name__ == '__main__':
    # copy existing county boundary if exists
    src_county = base / 'Data' / 'pa_counties.geojson'
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

    build_tileset_placeholders()
    build_state_senate_tileset(data_dir / 'tileset' / 'pa_state_senate_2022_lines_tileset.geojson')
    vtd_block_counts = load_vtd_block_counts_from_blockassign(
        base / 'Data' / 'BlockAssign_ST42_PA.zip',
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

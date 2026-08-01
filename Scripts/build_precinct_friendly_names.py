"""Build the county-scoped PA precinct friendly-name index from Census VTD data."""

import json
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCE = DATA / 'tl_2020_42_vtd20.zip'
OUTPUT = DATA / 'precinct_friendly_names.json'


def main():
    source = gpd.read_file(f'zip://{SOURCE}')
    required = {'COUNTYFP20', 'VTDST20', 'NAME20'}
    missing = required - set(source.columns)
    if missing:
        raise SystemExit(f'Missing expected Census VTD columns: {sorted(missing)}')

    counties = {}
    for _, row in source.iterrows():
        county = str(row['COUNTYFP20'] or '').strip().zfill(3)
        code = str(row['VTDST20'] or '').strip().upper()
        name = str(row['NAME20'] or '').strip()
        if county and code and name:
            counties.setdefault(county, {})[code] = name

    # Convert FIPS keys to the same county names used by the app's lookup maps.
    county_geojson = json.loads((DATA / 'pa_counties.geojson').read_text(encoding='utf-8'))
    fips_to_name = {}
    for feature in county_geojson.get('features', []):
        props = feature.get('properties') or {}
        fips = str(props.get('COUNTYFP20') or props.get('COUNTYFP') or '').strip().zfill(3)
        name = str(props.get('county') or props.get('NAME20') or props.get('NAME') or props.get('county_nam') or '').strip()
        if fips and name:
            fips_to_name[fips] = name.upper()

    named_counties = {
        fips_to_name.get(fips, fips): codes
        for fips, codes in sorted(counties.items())
    }
    payload = {
        'version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'generated_from': ['data/tl_2020_42_vtd20.zip'],
        'counties': dict(sorted(named_counties.items())),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {sum(len(v) for v in named_counties.values())} names across {len(named_counties)} counties to {OUTPUT}')


if __name__ == '__main__':
    main()

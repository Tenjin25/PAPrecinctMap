"""Build the county-scoped PA precinct friendly-name index from Census VTD data."""

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
SOURCE = DATA / 'tl_2020_42_vtd20.zip'
LIVE_SOURCE = DATA / 'pa_live_voting_districts_current.geojson'
OUTPUT = DATA / 'precinct_friendly_names.json'


def census_display_name(raw):
    """Keep Census naming structure while making JSON labels readable."""
    words = re.split(r'(\s+|-)', str(raw or '').strip().lower())
    abbreviations = {
        'twp': 'TWP', 'wd': 'WD', 'pct': 'PCT', 'vtd': 'VTD',
        'dist': 'DIST', 'ed': 'ED', 'cd': 'CD', 'bo': 'BO', 'boro': 'BORO',
    }
    out = []
    for word in words:
        if not word or word.isspace() or word == '-':
            out.append(word)
            continue
        key = word.rstrip('.').lower()
        if key in abbreviations:
            out.append(abbreviations[key] + ('.' if word.endswith('.') else ''))
        elif word.startswith("o'") and len(word) > 2:
            out.append("O'" + word[2].upper() + word[3:])
        elif word.startswith('mc') and len(word) > 2:
            out.append('Mc' + word[2].upper() + word[3:])
        else:
            out.append(word[:1].upper() + word[1:])
    return ''.join(out)


def main():
    counties = {}
    generated_from = [str(SOURCE.relative_to(ROOT))]
    source = gpd.read_file(f'zip://{SOURCE}')
    required = {'COUNTYFP20', 'VTDST20', 'NAME20'}
    missing = required - set(source.columns)
    if missing:
        raise SystemExit(f'Missing expected Census VTD columns: {sorted(missing)}')

    for _, row in source.iterrows():
        county = str(row['COUNTYFP20'] or '').strip().zfill(3)
        code = str(row['VTDST20'] or '').strip().upper()
        name = str(row['NAME20'] or '').strip()
        if county and code and name:
            counties.setdefault(county, {})[code] = census_display_name(name)

    # Overlay newer local names without dropping Census precincts that are not
    # present in the live extract.
    if LIVE_SOURCE.exists():
        live = json.loads(LIVE_SOURCE.read_text(encoding='utf-8'))
        for feature in live.get('features', []):
            props = feature.get('properties') or {}
            county = re.sub(r'\D', '', str(props.get('COUNTY') or '')).zfill(3)[-3:]
            code = re.sub(r'\D', '', str(props.get('VTD') or '')).zfill(6)
            name = str(props.get('NAME') or '').strip()
            if county and code and name:
                counties.setdefault(county, {}).setdefault(code, census_display_name(name))
        generated_from.append(str(LIVE_SOURCE.relative_to(ROOT)))

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
        'generated_from': generated_from,
        'counties': dict(sorted(named_counties.items())),
    }
    OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    subprocess.run([sys.executable, str(Path(__file__).with_name('build_precinct_alias_index.py'))], check=True)
    print(f'Wrote {sum(len(v) for v in named_counties.values())} names across {len(named_counties)} counties to {OUTPUT}')


if __name__ == '__main__':
    main()

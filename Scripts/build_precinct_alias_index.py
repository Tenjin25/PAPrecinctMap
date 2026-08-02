"""Build the PA county-scoped precinct alias index used by the map join."""

import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
FRIENDLY = DATA / 'precinct_friendly_names.json'
OUTPUT = DATA / 'precinct_alias_index.json'


def aliases_for(value):
    raw = str(value or '').strip().upper()
    if not raw:
        return set()
    out = {raw, re.sub(r'[^A-Z0-9]', '', raw)}
    normalized = re.sub(r'\s+', ' ', re.sub(r'[-_.]+', ' ', raw)).strip()
    if normalized:
        out.add(normalized)
        out.add(re.sub(r'[^A-Z0-9]', '', normalized))
    if raw.isdigit():
        number = str(int(raw))
        out.update({number, number.zfill(2), number.zfill(3), number.zfill(4), number.zfill(6)})
    # Pennsylvania election exports commonly repeat a municipality breakdown
    # (for example, "CONEWAGO X 1 X 1") and abbreviate District/Ward.
    collapsed = re.sub(r'\s+([A-Z])\s+(\d+)\s+\1\s+\2$', r' \1 \2', raw)
    if collapsed != raw:
        out.update(aliases_for(collapsed))
    for word, short in (('DISTRICT', 'D'), ('WARD', 'W'), ('PRECINCT', 'P')):
        if word in raw:
            out.update(aliases_for(raw.replace(word, short)))
            m_word = re.search(rf'\b{word}\s+0*(\d+)\b', raw)
            if m_word:
                n = int(m_word.group(1))
                # Election exports can repeat the breakdown as CODE N CODE N.
                out.add(re.sub(rf'\b{word}\s+0*\d+\b', f'{short} {n} {short} {n}', raw, count=1))
                if word == 'DISTRICT':
                    out.add(re.sub(r'\bDISTRICT\s+0*\d+\b', f'X {n} X {n}', raw, count=1))
    base_name = re.split(r'\s+(?:DISTRICT|WARD|PRECINCT)\b', raw, maxsplit=1)[0].strip()
    if base_name and base_name != raw:
        out.update(aliases_for(base_name))
    ward_precinct = re.search(r'\bWARD\s+0*(\d+)\s+PRECINCT\s+0*(\d+)\b', raw)
    if ward_precinct:
        a, b = int(ward_precinct.group(1)), int(ward_precinct.group(2))
        out.add(re.sub(r'\bWARD\s+0*\d+\s+PRECINCT\s+0*\d+\b', f'W {a} W {b}', raw, count=1))
    if raw.startswith('MOUNT '):
        out.update(aliases_for('MT ' + raw[6:]))
    if raw.startswith('MC') and not raw.startswith('MC '):
        out.update(aliases_for('MC ' + raw[2:]))
    m = re.search(r'\b(D|W|X|P)\s+0*(\d+)\b', raw)
    if m:
        out.add(re.sub(r'\b(D|W|X|P)\s+0*\d+\b', f'{m.group(1)} {int(m.group(2))}', raw, count=1))
    return {item for item in out if item}


def main():
    payload = json.loads(FRIENDLY.read_text(encoding='utf-8'))
    counties = {}
    for county, code_map in (payload.get('counties') or {}).items():
        aliases = defaultdict(set)
        for code, friendly_name in (code_map or {}).items():
            code = str(code or '').strip().upper()
            for alias in aliases_for(code) | aliases_for(friendly_name):
                aliases[alias].add(code)
        counties[county] = {alias: sorted(codes) for alias, codes in sorted(aliases.items())}

    output = {
        'version': 1,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'generated_from': ['data/precinct_friendly_names.json'],
        'counties': dict(sorted(counties.items())),
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'Wrote {sum(len(v) for v in counties.values())} county alias maps to {OUTPUT}')


if __name__ == '__main__':
    main()

"""Read saved Dauphin County precinct-by-ballot result tables."""

from __future__ import annotations

import html
import re
from pathlib import Path


SOURCE_DIR = Path(__file__).resolve().parents[1] / "data/source_reports/2026_general"
TABLE = re.compile(
    r'<tr class="font-weight-bolder">\s*<td class="padding uppercase"[^>]*>(.*?)</td>.*?'
    r'<table class="table border-leftnone ml-1"[^>]*>(.*?)</table>', re.S,
)


def read_dauphin(path: Path) -> dict[str, dict[str, tuple[int, int, int, int]]]:
    if b"OFFICIAL RESULTS" not in (SOURCE_DIR / "dauphin_index.html").read_bytes():
        raise ValueError("Dauphin site is not marked official")
    source = path.read_text(encoding="utf-8")
    result = {}
    for raw_name, raw_table in TABLE.findall(source):
        precinct = html.unescape(re.sub(r"<[^>]*>", "", raw_name)).strip()
        if precinct in result:
            raise ValueError(f"Duplicate Dauphin precinct: {path.name} {precinct}")
        candidates = {}
        for raw_row in re.findall(r"<tr[^>]*>(.*?)</tr>", raw_table, re.S):
            cells = [html.unescape(re.sub(r"<[^>]*>", "", cell)).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", raw_row, re.S)]
            if len(cells) != 5 or not cells[0] or not all(value.isdigit() for value in cells[1:]):
                continue
            name = cells[0].upper()
            election_day, mail, provisional, total = map(int, cells[1:])
            if total != election_day + mail + provisional:
                raise ValueError(f"Dauphin vote split differs: {path.name} {precinct} {name}")
            if name in candidates:
                raise ValueError(f"Duplicate Dauphin candidate: {path.name} {precinct} {name}")
            candidates[name] = (total, election_day, mail, provisional)
        if candidates:
            result[precinct] = candidates
    if not result:
        raise ValueError(f"No Dauphin precincts found: {path.name}")
    return result

"""Save Dauphin County's official 2026 precinct-by-ballot pages."""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
from pathlib import Path


BASE = "https://elections.dauphincounty.gov"
DEST = Path(__file__).resolve().parents[1] / "data/source_reports/2026_general"
FILTERS = (
    "GOVERNOR AND LT GOVERNOR", "REPRESENTATIVE IN CONGRESS", "STATE SEN 34",
    "HD 103", "HD 104", "HD 105", "HD 106", "HD 125",
)


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    index = fetch(f"{BASE}/?key=42")
    if b"OFFICIAL RESULTS" not in index:
        raise ValueError("Dauphin 2026 site is not marked official")
    (DEST / "dauphin_index.html").write_bytes(index)
    for label in FILTERS:
        page = fetch(f"{BASE}/?" + urllib.parse.urlencode({"key": "42", "race": label}))
        match = re.search(rb'href="(/PreceinctByBallot\?key=42&amp;race=[^"]+)"', page)
        if not match:
            raise ValueError(f"Dauphin precinct page missing for {label}")
        path = html.unescape(match[1].decode("utf-8"))
        saved = DEST / ("dauphin_" + re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") + ".html")
        saved.write_bytes(fetch(BASE + path))
        print(saved.name, saved.stat().st_size)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reconcile existing district presidential files to statewide party totals."""

import json
from pathlib import Path

import regenerate_pa_district_jsons_from_crosswalks as regenerate


ROOT = Path(__file__).resolve().parents[1]
DISTRICTS = ROOT / "data" / "district_contests"


def main():
    for path in sorted(DISTRICTS.glob("*_president_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        year = int(document["year"])
        results = document["general"]["results"]
        source = regenerate.apply_statewide_vote_control("president", year, results)
        if not source:
            continue
        marker = f"statewide_vote_control/{source}"
        current_source = document.setdefault("meta", {}).get("source", "")
        if marker not in current_source:
            document["meta"]["source"] = f"{current_source}+{marker}" if current_source else marker
        path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"calibrated {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Reconcile existing district presidential files to statewide party totals."""

import argparse
import json
from pathlib import Path

import regenerate_pa_district_jsons_from_crosswalks as regenerate


ROOT = Path(__file__).resolve().parents[1]
DISTRICTS = ROOT / "data" / "district_contests"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--years", nargs="+", type=int)
    args = parser.parse_args()
    for path in sorted(DISTRICTS.glob("*_president_*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        year = int(document["year"])
        if args.years and year not in args.years:
            continue
        results = document["general"]["results"]
        raw_source = ROOT / "data" / f"ElectionReturns_{year}_General_PrecinctReturns.txt"
        controls = None
        source_override = ""
        if raw_source.exists():
            rows, _candidates = regenerate.parse_precinct_returns(raw_source, year, "USP")
            controls = {
                f"{bucket}_votes": round(sum(float(values.get(bucket) or 0) for values in rows.values()))
                for bucket in ("dem", "rep", "other")
            }
            source_override = raw_source.name
        source = regenerate.apply_statewide_vote_control(
            "president", year, results, controls, source_override
        )
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

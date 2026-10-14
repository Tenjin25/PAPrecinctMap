#!/usr/bin/env python3
"""Reconcile existing district files to independent statewide party totals."""

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
    control_cache = {}
    for path in sorted(DISTRICTS.glob("*.json")):
        if path.name == "manifest.json":
            continue
        document = json.loads(path.read_text(encoding="utf-8"))
        year = int(document["year"])
        if args.years and year not in args.years:
            continue
        contest = str(document.get("contest_type") or "")
        results = document["general"]["results"]
        raw_source = ROOT / "data" / f"ElectionReturns_{year}_General_PrecinctReturns.txt"
        cache_key = (year, contest)
        controls, source_override = control_cache.get(cache_key, (None, ""))
        if cache_key not in control_cache:
            for stem in ("vest", "rdh"):
                audit_path = ROOT / "data" / f"{stem}_{year}_district_vote_audit.json"
                if not audit_path.exists():
                    continue
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                candidate = (audit.get("controls") or {}).get(contest)
                if isinstance(candidate, dict):
                    controls = {
                        field: int(candidate[field])
                        for field in ("dem_votes", "rep_votes", "other_votes")
                    }
                    source_override = audit_path.relative_to(ROOT / "data").as_posix()
                    break
            office_code = {
                "president": "USP",
                "us_senate": "USS",
                "governor": "GOV",
                "attorney_general": "ATT",
                "auditor": "AUD",
                "treasurer": "TRE",
            }.get(contest)
            if controls is None and raw_source.exists() and office_code:
                rows, _candidates = regenerate.parse_precinct_returns(raw_source, year, office_code)
                controls = {
                    f"{bucket}_votes": round(sum(float(values.get(bucket) or 0) for values in rows.values()))
                    for bucket in ("dem", "rep", "other")
                }
                source_override = raw_source.name
            control_cache[cache_key] = (controls, source_override)
        source = regenerate.apply_statewide_vote_control(
            contest, year, results, controls, source_override
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

"""Freeze reviewed baseline examples; refuses to replace an existing fixture."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
import build_county_clustered_2024_district_contests as clustered


def main():
    target = ROOT / "data/benchmarks/current_plan_reconciliation.json"
    if target.exists():
        raise FileExistsError("Fixture exists; review changes before replacing it")
    data = ROOT / "data"
    candidate = data / "district_bef_candidate"
    maps, counties, _, _ = clustered.build_vap_maps(
        data / "crosswalks/pa_block20_vap.csv.gz", data / "BlockAssign_ST42_PA.zip")
    fixture = {"baseline_commit": "0577735", "decision": "retain published pending attribution",
               "benchmarks": [], "split_counties": []}
    for year, district in ((2024, "8"), (2018, "10")):
        filename = f"congressional_us_senate_{year}.json"
        example = {"year": year, "district": district, "scope": "congressional", "contest": "us_senate"}
        for label, folder in (("published", data / "district_contests"), ("candidate", candidate)):
            payload = json.loads((folder / filename).read_text(encoding="utf-8"))
            example[label] = payload["general"]["results"][district]
        fixture["benchmarks"].append(example)
    for scope, county, name in (("congressional", "079", "LUZERNE"),
                               ("state_house", "101", "PHILADELPHIA"),
                               ("state_senate", "069", "LACKAWANNA")):
        weights = {}
        vtds = {}
        for (countyfp, vtd), destinations in maps[scope].items():
            if countyfp != county:
                continue
            vtds[vtd] = dict(destinations)
            for district, vap in destinations.items():
                weights[district] = weights.get(district, 0) + vap
        payload = json.loads((candidate / f"{scope}_us_senate_2024.json").read_text(encoding="utf-8"))
        fixture["split_counties"].append({"scope": scope, "county_fips": county, "county": name,
                                           "material_districts": sorted(counties[scope][county], key=int),
                                           "vap_by_district": weights, "vtd_weights": vtds,
                                           "candidate_county_audit": payload["meta"]["county_conservation_audit"]["counties"][name]})
    target.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()

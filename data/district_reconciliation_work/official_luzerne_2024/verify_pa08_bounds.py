"""Derive congressional bounds from official county contest membership."""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = HERE.parent


def main():
    details = {row["K"]: row for row in json.loads((HERE / "details.json").read_text())["Contests"]}
    senate = dict(zip(details["2"]["P"], details["2"]["V"]))
    cd8, cd9 = set(details["6"]["P"]), set(details["7"]["P"])
    assert set(senate) == cd8 | cd9
    overlap = cd8 & cd9
    assert overlap == {"Butler Township Dist 05"}
    fixed = [sum(senate[precinct][index] for precinct in cd8 - cd9) for index in range(5)]
    pooled = [sum(senate[precinct][index] for precinct in overlap) for index in range(5)]
    lower = {"dem_votes": fixed[0], "rep_votes": fixed[1], "other_votes": sum(fixed[2:])}
    pool = {"dem_votes": pooled[0], "rep_votes": pooled[1], "other_votes": sum(pooled[2:])}
    root = WORK.parents[1]
    fixture = json.loads((root / "data/benchmarks/luzerne_2024_senate_precinct_bounds.json").read_text())
    assert fixture["pooled_votes"] == pool
    assert fixture["fixed_votes"]["8"] == lower
    fixed9 = [sum(senate[precinct][index] for precinct in cd9 - cd8) for index in range(5)]
    assert fixture["fixed_votes"]["9"] == {"dem_votes": fixed9[0], "rep_votes": fixed9[1], "other_votes": sum(fixed9[2:])}
    assert fixture["county_votes"] == {field: lower[field] + pool[field] + fixture["fixed_votes"]["9"][field] for field in lower}
    candidate = json.loads((root / "data/district_bef_candidate/congressional_us_senate_2024.json").read_text())
    actual = candidate["meta"]["county_conservation_audit"]["counties"]["LUZERNE"]["district_allocations"]["8"]
    published = {}
    with (WORK / "benchmark_ledgers/pa08_published_fractional_counties.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["county"] == "LUZERNE":
                published[row["party_bucket"]] = float(row["votes"])
    result = []
    for field in lower:
        upper = lower[field] + pool[field]
        modeled = lower[field] + pool[field] * 403 / 1390
        assert abs(modeled - published[field]) < 1e-7
        result.append({"party_bucket": field, "official_unsplit_cd8": lower[field],
                       "official_pooled_precinct": pool[field], "maximum_possible_cd8": upper,
                       "published_fractional_cd8": published[field], "candidate_cd8": actual[field],
                       "candidate_exceeds_upper_bound": actual[field] - upper})
    with (HERE / "pa08_official_county_bounds.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

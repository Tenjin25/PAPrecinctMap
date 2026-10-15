"""Fetch official named-candidate county controls for modern PA elections."""
from __future__ import annotations

import argparse
import csv
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
API = "https://www.electionreturns.pa.gov/api/ElectionReturn/GetCountyData"
SUMMARY_API = "https://www.electionreturns.pa.gov/api/ElectionReturn/GET"
ELECTIONS = {2020: 83, 2022: 94, 2024: 105}
OFFICES = {
    "President of the United States": "president",
    "President": "president",
    "United States Senator": "us_senate",
    "Governor": "governor",
    "Attorney General": "attorney_general",
    "Auditor General": "auditor",
    "State Treasurer": "treasurer",
}
COUNTIES = (
    "ADAMS", "ALLEGHENY", "ARMSTRONG", "BEAVER", "BEDFORD", "BERKS", "BLAIR", "BRADFORD", "BUCKS", "BUTLER",
    "CAMBRIA", "CAMERON", "CARBON", "CENTRE", "CHESTER", "CLARION", "CLEARFIELD", "CLINTON", "COLUMBIA", "CRAWFORD",
    "CUMBERLAND", "DAUPHIN", "DELAWARE", "ELK", "ERIE", "FAYETTE", "FOREST", "FRANKLIN", "FULTON", "GREENE",
    "HUNTINGDON", "INDIANA", "JEFFERSON", "JUNIATA", "LACKAWANNA", "LANCASTER", "LAWRENCE", "LEBANON", "LEHIGH", "LUZERNE",
    "LYCOMING", "MCKEAN", "MERCER", "MIFFLIN", "MONROE", "MONTGOMERY", "MONTOUR", "NORTHAMPTON", "NORTHUMBERLAND", "PERRY",
    "PHILADELPHIA", "PIKE", "POTTER", "SCHUYLKILL", "SNYDER", "SOMERSET", "SULLIVAN", "SUSQUEHANNA", "TIOGA", "UNION",
    "VENANGO", "WARREN", "WASHINGTON", "WAYNE", "WESTMORELAND", "WYOMING", "YORK",
)


def payload(url: str):
    with urlopen(url, timeout=60) as response:
        outer = json.loads(response.read().decode("utf-8"))
    return json.loads(outer) if isinstance(outer, str) else outer


def candidate_bucket(party: str) -> str:
    party = str(party or "").strip().upper()
    return "dem_votes" if party.startswith("DEM") else "rep_votes" if party.startswith("REP") else "other_votes"


def county_rows(year: int, county: str) -> list[dict]:
    election_id = ELECTIONS[year]
    query = urlencode({"countyName": county, "methodName": "General", "electionid": election_id, "electiontype": "G", "isactive": 0})
    document = payload(f"{API}?{query}")
    groups = next(iter(document["Election"].values()))
    rows = []
    for group in groups:
        for office, district_groups in group.items():
            contest = OFFICES.get(office.strip())
            if not contest:
                continue
            totals = {"dem_votes": 0, "rep_votes": 0, "other_votes": 0}
            for district_group in district_groups or []:
                for district in district_group.get("Districts", []) or []:
                    for candidate in district.get("Candidates", []) or []:
                        totals[candidate_bucket(candidate.get("PartyName"))] += int(candidate.get("Votes") or 0)
            rows.append({"year": year, "contest": contest, "county": county.title(), **totals, "total_votes": sum(totals.values())})
    return rows


def statewide_controls(year: int) -> dict[str, dict[str, int]]:
    query = urlencode({"methodName": "GetSummaryData", "electionid": ELECTIONS[year], "electiontype": "G", "isactive": 0})
    election = payload(f"{SUMMARY_API}?{query}")["Election"]
    result = {}
    for office, groups in election.items():
        contest = OFFICES.get(office.strip())
        if not contest:
            continue
        totals = {"dem_votes": 0, "rep_votes": 0, "other_votes": 0}
        for group in groups or []:
            for candidate in group.get("Statewide", []) or []:
                totals[candidate_bucket(candidate.get("PartyName"))] += int(candidate.get("Votes") or 0)
        result[contest] = totals
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, choices=sorted(ELECTIONS), required=True)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "benchmarks")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for year in args.years:
        rows = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(county_rows, year, county): county for county in COUNTIES}
            for future in as_completed(futures):
                rows.extend(future.result())
        statewide = statewide_controls(year)
        for contest in sorted({row["contest"] for row in rows}):
            contest_rows = sorted((row for row in rows if row["contest"] == contest), key=lambda row: row["county"])
            if len(contest_rows) != 67:
                raise RuntimeError(f"{year} {contest}: expected 67 counties, got {len(contest_rows)}")
            actual = {field: sum(row[field] for row in contest_rows) for field in ("dem_votes", "rep_votes", "other_votes")}
            if actual != statewide.get(contest):
                raise RuntimeError(f"{year} {contest}: county sum {actual} != statewide {statewide.get(contest)}")
            path = args.output_dir / f"pa_county_{year}_{contest}_certified.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=("county", "dem_votes", "rep_votes", "other_votes", "total_votes"), lineterminator="\n")
                writer.writeheader()
                writer.writerows({key: row[key] for key in writer.fieldnames} for row in contest_rows)
            print(f"{path}: {actual}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

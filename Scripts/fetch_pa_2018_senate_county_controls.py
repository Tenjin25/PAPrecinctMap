"""Fetch certified 2018 U.S. Senate named-candidate totals by county.

Pennsylvania's summary and county APIs exclude write-ins from their candidate
rows and percentage denominator.  This file intentionally controls the three
atlas party buckets (Democratic, Republican, and named third-party candidates)
without inventing a geographic distribution for the 1,568 statewide write-ins.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


API = "https://www.electionreturns.pa.gov/api/ElectionReturn/GetCountyData"
ELECTION_ID = 63
COUNTIES = (
    "ADAMS", "ALLEGHENY", "ARMSTRONG", "BEAVER", "BEDFORD", "BERKS", "BLAIR", "BRADFORD", "BUCKS", "BUTLER",
    "CAMBRIA", "CAMERON", "CARBON", "CENTRE", "CHESTER", "CLARION", "CLEARFIELD", "CLINTON", "COLUMBIA", "CRAWFORD",
    "CUMBERLAND", "DAUPHIN", "DELAWARE", "ELK", "ERIE", "FAYETTE", "FOREST", "FRANKLIN", "FULTON", "GREENE",
    "HUNTINGDON", "INDIANA", "JEFFERSON", "JUNIATA", "LACKAWANNA", "LANCASTER", "LAWRENCE", "LEBANON", "LEHIGH", "LUZERNE",
    "LYCOMING", "MCKEAN", "MERCER", "MIFFLIN", "MONROE", "MONTGOMERY", "MONTOUR", "NORTHAMPTON", "NORTHUMBERLAND", "PERRY",
    "PHILADELPHIA", "PIKE", "POTTER", "SCHUYLKILL", "SNYDER", "SOMERSET", "SULLIVAN", "SUSQUEHANNA", "TIOGA", "UNION",
    "VENANGO", "WARREN", "WASHINGTON", "WAYNE", "WESTMORELAND", "WYOMING", "YORK",
)
EXPECTED = {"dem_votes": 2_792_437, "rep_votes": 2_134_848, "other_votes": 82_115}


def fetch_county(county: str) -> dict[str, int | str]:
    query = urlencode({
        "countyName": county, "methodName": "General", "electionid": ELECTION_ID,
        "electiontype": "G", "isactive": 0,
    })
    with urlopen(f"{API}?{query}", timeout=45) as response:
        outer = json.loads(response.read().decode("utf-8"))
    payload = json.loads(outer) if isinstance(outer, str) else outer
    # The API spells McKean with mixed case while accepting an uppercase query.
    offices = next(iter(payload["Election"].values()))
    senate = next(group["United States Senator"] for group in offices if "United States Senator" in group)
    candidates = senate[0]["Districts"][0]["Candidates"]
    totals = {"dem_votes": 0, "rep_votes": 0, "other_votes": 0}
    for candidate in candidates:
        party = str(candidate.get("PartyName") or "").upper()
        bucket = "dem_votes" if party == "DEM" else "rep_votes" if party == "REP" else "other_votes"
        totals[bucket] += int(candidate.get("Votes") or 0)
    return {"county": county.title(), **totals, "total_votes": sum(totals.values())}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = [fetch_county(county) for county in COUNTIES]
    actual = {field: sum(int(row[field]) for row in rows) for field in EXPECTED}
    if actual != EXPECTED:
        raise RuntimeError(f"official county totals {actual} do not match statewide controls {EXPECTED}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"counties": len(rows), "totals": actual}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

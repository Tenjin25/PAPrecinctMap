"""Fetch complete county-level judicial results from Pennsylvania's public API.

The Department of State bulk precinct exports for 2011 and 2015 omit or
misclassify some judicial results.  The historical results API exposes the
official county return for every statewide office, including each candidate in
multi-winner contests and the separate Yes/No totals in retention contests.
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "pa_historical_judicial_county_results.json"
API = "https://www.electionreturns.pa.gov/api/ElectionReturn/GetCountyData"
COUNTIES = (
    "ADAMS", "ALLEGHENY", "ARMSTRONG", "BEAVER", "BEDFORD", "BERKS", "BLAIR", "BRADFORD", "BUCKS", "BUTLER",
    "CAMBRIA", "CAMERON", "CARBON", "CENTRE", "CHESTER", "CLARION", "CLEARFIELD", "CLINTON", "COLUMBIA", "CRAWFORD",
    "CUMBERLAND", "DAUPHIN", "DELAWARE", "ELK", "ERIE", "FAYETTE", "FOREST", "FRANKLIN", "FULTON", "GREENE",
    "HUNTINGDON", "INDIANA", "JEFFERSON", "JUNIATA", "LACKAWANNA", "LANCASTER", "LAWRENCE", "LEBANON", "LEHIGH", "LUZERNE",
    "LYCOMING", "MCKEAN", "MERCER", "MIFFLIN", "MONROE", "MONTGOMERY", "MONTOUR", "NORTHAMPTON", "NORTHUMBERLAND", "PERRY",
    "PHILADELPHIA", "PIKE", "POTTER", "SCHUYLKILL", "SNYDER", "SOMERSET", "SULLIVAN", "SUSQUEHANNA", "TIOGA", "UNION",
    "VENANGO", "WARREN", "WASHINGTON", "WAYNE", "WESTMORELAND", "WYOMING", "YORK",
)
ELECTIONS = {2011: 20, 2015: 43}
COURT_TERMS = ("supreme court", "superior court", "commonwealth court")


def integer(value) -> int:
    try:
        return int(str(value or "0").replace(",", ""))
    except ValueError:
        return 0


def person_name(value: str) -> str:
    parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
    raw = " ".join(reversed(parts)) if len(parts) > 1 else (parts[0] if parts else "")
    words = []
    for word in raw.split():
        stem = word.rstrip(".")
        if len(stem) == 1 and stem.isalpha():
            words.append(stem.upper() + ".")
        elif stem.upper() in {"JR", "SR"}:
            words.append(stem.title() + ".")
        else:
            title = stem[:1].upper() + stem[1:].lower()
            if len(title) > 3 and title.lower().startswith("mc"):
                title = "Mc" + title[2:3].upper() + title[3:]
            words.append(title)
    return " ".join(words)


def county_rows(year: int, election_id: int, county: str) -> list[dict]:
    query = urlencode({
        "countyName": county,
        "methodName": "General",
        "electionid": election_id,
        "electiontype": "G",
        "isactive": 0,
    })
    with urlopen(f"{API}?{query}", timeout=45) as response:
        outer = json.loads(response.read().decode("utf-8"))
    payload = json.loads(outer) if isinstance(outer, str) else outer
    election = payload.get("Election", {}) if isinstance(payload, dict) else {}
    records = []
    for offices in election.values():
        for office_group in offices or []:
            for office, district_groups in office_group.items():
                if not any(term in office.lower() for term in COURT_TERMS):
                    continue
                for district_group in district_groups or []:
                    for district in district_group.get("Districts", []) or []:
                        for candidate in district.get("Candidates", []) or []:
                            retention = str(candidate.get("IsRetention") or "") == "1"
                            records.append({
                                "year": year,
                                "county": county,
                                "office": office.strip(),
                                "district": str(district.get("District") or "").strip(),
                                "candidate": person_name(candidate.get("CandidateName")),
                                "party": str(candidate.get("PartyName") or "").strip(),
                                "is_retention": retention,
                                "votes": integer(candidate.get("Votes")),
                                "yes_votes": integer(candidate.get("YesVotes")),
                                "no_votes": integer(candidate.get("NoVotes")),
                            })
    return records


def main() -> int:
    results = {"source": API, "scope": "official_county_returns", "elections": {}}
    for year, election_id in ELECTIONS.items():
        rows = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(county_rows, year, election_id, county): county for county in COUNTIES}
            for future in as_completed(futures):
                county = futures[future]
                try:
                    rows.extend(future.result())
                except Exception as exc:
                    raise RuntimeError(f"{year} {county}: {exc}") from exc
        results["elections"][str(year)] = {"election_id": election_id, "rows": rows}
        print(f"{year}: {len(rows):,} judicial county records")
    OUTPUT.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

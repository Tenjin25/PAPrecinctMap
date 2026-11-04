#!/usr/bin/env python3
"""Fetch Pennsylvania's current unofficial 2026 governor results by county.

The Department of State API returns JSON encoded inside a JSON string.  This
script normalizes that response into the county-contest schema used by the map,
updates the contest manifest, and mirrors the data into the aggregate fallback.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
CONTEST_DIR = DATA_DIR / "contests"
ELECTION_ID = 117
ELECTION_URL = (
    "https://www.electionreturns.pa.gov/api/ElectionReturn/GetCountyBreak"
    "?officeId=3&districtId=1&methodName=GetCountyBreak"
    f"&electionid={ELECTION_ID}&electiontype=G&isactive=1"
)


def fetch_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "PAPrecinctMap/1.0"})
    with urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        raise ValueError("The election-return endpoint did not return an object")
    return payload


def title_candidate(value: str) -> str:
    return " ".join(part.capitalize() for part in value.strip().split())


def build_rows(payload: dict) -> tuple[list[dict], dict[str, dict]]:
    statewide = payload.get("Election", {}).get("Statewide") or []
    if len(statewide) != 1 or not isinstance(statewide[0], dict):
        raise ValueError("Unexpected county-results response shape")

    rows: list[dict] = []
    aggregate_results: dict[str, dict] = {}
    for county, candidates in sorted(statewide[0].items()):
        by_party = {str(c.get("PartyName", "")).upper(): c for c in candidates}
        dem = by_party.get("DEM")
        rep = by_party.get("REP")
        if not dem or not rep:
            raise ValueError(f"Missing major-party result for {county}")

        dem_votes = int(dem.get("Votes") or 0)
        rep_votes = int(rep.get("Votes") or 0)
        other_votes = sum(
            int(c.get("Votes") or 0)
            for party, c in by_party.items()
            if party not in {"DEM", "REP"}
        )
        total_votes = dem_votes + rep_votes + other_votes
        margin = abs(dem_votes - rep_votes)
        winner = "D" if dem_votes > rep_votes else "R" if rep_votes > dem_votes else ""
        dem_candidate = title_candidate(str(dem.get("CandidateName") or ""))
        rep_candidate = title_candidate(str(rep.get("CandidateName") or ""))
        node = {
            "dem_votes": dem_votes,
            "rep_votes": rep_votes,
            "other_votes": other_votes,
            "total_votes": total_votes,
            "dem_candidate": dem_candidate,
            "rep_candidate": rep_candidate,
            "margin": float(margin),
            "margin_pct": (margin / total_votes * 100) if total_votes else 0.0,
            "winner": winner,
        }
        aggregate_results[county.upper()] = dict(node)
        rows.append(
            {
                "county": county.upper(),
                **node,
                "color": (
                    "#2563eb" if winner == "D" else "#dc2626" if winner == "R" else "#6b7280"
                ),
            }
        )

    if len(rows) != 67:
        raise ValueError(f"Expected 67 counties, received {len(rows)}")
    return rows, aggregate_results


def update_manifest(retrieved_at: str) -> None:
    path = CONTEST_DIR / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    files = manifest.setdefault("files", [])
    files[:] = [
        entry
        for entry in files
        if not (entry.get("contest_type") == "governor" and int(entry.get("year", 0)) == 2026)
    ]
    files.append(
        {
            "contest_type": "governor",
            "year": 2026,
            "file": "governor_2026.json",
            "rows": 67,
            "status": "unofficial",
            "source": "Pennsylvania Department of State election returns",
            "source_url": ELECTION_URL,
            "retrieved_at": retrieved_at,
        }
    )
    files.sort(key=lambda entry: (int(entry.get("year", 0)), str(entry.get("contest_type", ""))))
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def update_aggregate(results: dict[str, dict], retrieved_at: str) -> None:
    path = DATA_DIR / "pa_elections_aggregated.json"
    aggregate = json.loads(path.read_text(encoding="utf-8"))
    year = aggregate.setdefault("results_by_year", {}).setdefault("2026", {})
    year["governor"] = {
        "statewide": {
            "status": "unofficial",
            "source": "Pennsylvania Department of State election returns",
            "source_url": ELECTION_URL,
            "retrieved_at": retrieved_at,
            "results": results,
        }
    }
    path.write_text(json.dumps(aggregate, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rows, aggregate_results = build_rows(fetch_json(ELECTION_URL))
    contest_payload = {
        "contest": "governor",
        "year": 2026,
        "status": "unofficial",
        "source": "Pennsylvania Department of State election returns",
        "source_url": ELECTION_URL,
        "retrieved_at": retrieved_at,
        "rows": rows,
    }
    (CONTEST_DIR / "governor_2026.json").write_text(
        json.dumps(contest_payload, indent=2) + "\n", encoding="utf-8"
    )
    update_manifest(retrieved_at)
    update_aggregate(aggregate_results, retrieved_at)

    totals = {
        "dem": sum(row["dem_votes"] for row in rows),
        "rep": sum(row["rep_votes"] for row in rows),
        "other": sum(row["other_votes"] for row in rows),
    }
    print(json.dumps({"counties": len(rows), "retrieved_at": retrieved_at, **totals}, indent=2))


if __name__ == "__main__":
    main()

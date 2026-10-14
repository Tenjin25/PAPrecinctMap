"""Build audited 2016 county and current-district contests from VEST geometry."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import geopandas as gpd

import regenerate_pa_district_jsons_from_crosswalks as district_builder


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONTESTS = {
    "president": ("USP", ("G16PREDCLI",), ("G16PRERTRU",), ("G16PRELJOH", "G16PREGSTE", "G16PRECCAS")),
    "us_senate": ("USS", ("G16USSDMCG",), ("G16USSRTOO",), ("G16USSLCLI",)),
    "attorney_general": ("ATT", ("G16ATGDSHA",), ("G16ATGRRAF",), ()),
    "auditor": ("AUD", ("G16AUDDDEP",), ("G16AUDRBRO",), ("G16AUDLMIN", "G16AUDGSWE")),
    "treasurer": ("TRE", ("G16TREDTOR",), ("G16TRERVOI",), ("G16TRELBAB", "G16TREGCOM")),
}
CANDIDATES = {
    "president": ("Hillary Clinton", "Donald J. Trump"),
    "us_senate": ("Katie McGinty", "Pat Toomey"),
    "attorney_general": ("Josh Shapiro", "John Rafferty"),
    "auditor": ("Eugene DePasquale", "John Brown"),
    "treasurer": ("Joe Torsella", "Otto Voit"),
}
COUNTY_NAMES = {
    str(row.COUNTYFP20).zfill(3): str(row.NAME20).strip().upper()
    for row in gpd.read_file(DATA / "pa_counties.geojson", columns=["COUNTYFP20", "NAME20"]).itertuples(index=False)
}


def sum_fields(row, fields):
    return round(sum(float(row.get(field) or 0) for field in fields))


def county_rows(frame, contest):
    _office, dem_fields, rep_fields, other_fields = CONTESTS[contest]
    dem_candidate, rep_candidate = CANDIDATES[contest]
    totals = defaultdict(lambda: {"dem_votes": 0, "rep_votes": 0, "other_votes": 0})
    for row in frame.to_dict("records"):
        county = COUNTY_NAMES[str(row["COUNTYFP"]).zfill(3)]
        totals[county]["dem_votes"] += sum_fields(row, dem_fields)
        totals[county]["rep_votes"] += sum_fields(row, rep_fields)
        totals[county]["other_votes"] += sum_fields(row, other_fields)
    rows = []
    for county, votes in sorted(totals.items()):
        total = sum(votes.values())
        margin = votes["dem_votes"] - votes["rep_votes"]
        winner = "D" if margin > 0 else "R" if margin < 0 else "T"
        rows.append({
            "county": county,
            **votes,
            "total_votes": total,
            "dem_candidate": dem_candidate,
            "rep_candidate": rep_candidate,
            "margin": float(abs(margin)),
            "margin_pct": abs(margin) / total * 100 if total else 0.0,
            "winner": winner,
            "color": "#2563eb" if winner == "D" else "#dc2626" if winner == "R" else "#6b7280",
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DATA / "historical_sources" / "vest_pa_2016.zip")
    parser.add_argument("--district-out", type=Path, default=DATA / "district_contests")
    parser.add_argument("--county-out", type=Path, default=DATA / "contests")
    parser.add_argument("--weight-mode", choices=("area", "block_count"), default="block_count")
    args = parser.parse_args()
    source = args.source.resolve()
    frame = gpd.read_file(f"zip://{source.as_posix()}", ignore_geometry=True)
    args.county_out.mkdir(parents=True, exist_ok=True)
    args.district_out.mkdir(parents=True, exist_ok=True)
    controls = {}
    official = DATA / "ElectionReturns_2016_General_PrecinctReturns.txt"
    for contest, (office, *_fields) in CONTESTS.items():
        rows = county_rows(frame, contest)
        county_path = args.county_out / f"{contest}_2016.json"
        county_path.write_text(json.dumps({"contest": contest, "year": 2016, "rows": rows}, indent=2) + "\n", encoding="utf-8")
        controls[contest] = {
            key: sum(row[key] for row in rows)
            for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
        }
        district_builder.build_one(
            2016, official, contest, office, args.district_out.resolve(), args.weight_mode,
            historical_vtd_source=source, historical_geometry_source=source,
        )
    audit = {
        "year": 2016,
        "source": str(source.relative_to(ROOT)).replace("\\", "/"),
        "method": "VEST precinct geometry intersected with VTD20; VTD20 assigned to current districts by block count",
        "controls": controls,
    }
    (DATA / "vest_2016_district_vote_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()

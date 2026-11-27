#!/usr/bin/env python3
"""Extract verified 2026 governor precinct returns from county reports.

These are county-published official reports, not the eventual Pennsylvania bulk file.
Only exact, unambiguous normalized precinct names are assigned to map geometry.
Unmatched names remain in the CSV and are listed in the audit output.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path

import pdfplumber


ROOT = Path(__file__).resolve().parents[1]
PDF_DIR = ROOT / "data" / "source_reports" / "2026_general"
OUT = ROOT / "data" / "Openelections" / "2026" / "20261103__pa__general__precinct_county_official.csv"
AUDIT = ROOT / "data" / "pa_2026_county_precinct_audit.json"
MANIFEST = ROOT / "data" / "precinct_returns_manifest.json"
SOURCES = {
    "BERKS": "https://www.berkspa.gov/getmedia/f2dde727-efd0-4e9e-b86f-ce73da4d7e05/GE2026-Precinct-Report.pdf",
    "CHESTER": "https://www.chesco.org/DocumentCenter/View/86455/CHESTER_2026-GENERAL_OFFICIAL-PRECINCT-RESULTS?bidId=",
    "FRANKLIN": "https://lfweb.franklincountypa.gov/Election%20Results/PrecinctDetail.pdf",
    "LAWRENCE": "https://www.lawrencecountypa.gov/getmedia/99327a61-5f14-4ab3-a690-cbc1884ef242/2026-General-Election-Official-Precinct-Report.pdf",
    "LEBANON": "https://www.lebanoncountypa.gov/getmedia/2814004b-ba3a-4a28-b8de-b08595f5059e/2026-General-FINAL-PRECINCT-SUMMARY-WITH-WRITE-INS_2.pdf",
    "LYCOMING": "https://lycomingcountypa.gov/Documents/Government/Departments/Voter%20Services/PreviousResults/2026GEPrecinct.pdf?t=202611121357080",
    "MERCER": "https://www.mercercountypa.gov/election/Election.Results/2026/GENERAL/Precinct.pdf",
    "MIFFLIN": "https://mifflincountypa.gov/getmedia/2469c096-4771-4df5-83ec-1472c5d6aefa/2026-November-General-Election-Official-Precinct-Results",
    "POTTER": "https://pottercountypa.gov/Documents/Departments/Voter%20Registration%20and%20Elections/2026/Results/Potter_OfficialResults_Precinct.pdf?t=202611171456210",
    "SUSQUEHANNA": "https://susqco.com/getmedia/d90196d5-9afb-4774-a131-fad9b0bd961b/2026-General-Official-Precinct-Report.pdf",
}
FIELDNAMES = ["county", "precinct", "office", "district", "party", "candidate", "votes", "election_day", "mail", "provisional"]
CANDIDATE = re.compile(r"^(DEM|REP|LIB) (.+?) ([\d,]+)(?: \d+(?:\.\d+)?%)? ([\d,]+) ([\d,]+) ([\d,]+)$")


def norm(value: str) -> str:
    value = value.upper().replace("&", " AND ")
    value = re.sub(r"\b(1ST|FIRST)\b", "1", value)
    value = re.sub(r"\b(2ND|SECOND)\b", "2", value)
    value = re.sub(r"\b(3RD|THIRD)\b", "3", value)
    value = re.sub(r"\b(\d+)(?:TH|ST|ND|RD)\b", r"\1", value)
    value = re.sub(r"\b(E|W|N|S)\b", lambda m: {"E": "EAST", "W": "WEST", "N": "NORTH", "S": "SOUTH"}[m.group()], value)
    value = re.sub(r"\bBOROUGH OF\b", "", value)
    value = re.sub(r"\b(TOWNSHIP|TWP|BOROUGH|BORO)\b", "", value)
    value = re.sub(r"\b(WARD|WD)\b", "WD", value)
    value = re.sub(r"\b(ED)\b", "", value)
    value = re.sub(r"\b(PRECINCT|PCT|DIST|VTD)\b", "", value)
    value = re.sub(r"\b0+(\d+)\b", r"\1", value)
    return re.sub(r"[^A-Z0-9]+", " ", value).strip()


ORDINALS = {"FIRST": "1", "SECOND": "2", "THIRD": "3", "FOURTH": "4", "FIFTH": "5", "SIXTH": "6", "SEVENTH": "7", "EIGHTH": "8", "NINTH": "9", "TENTH": "10"}


def source_norm(county: str, name: str) -> str:
    value = name.upper()
    if county == "CHESTER":
        value = re.sub(r"^\d{3}\s+", "", value)
    if county == "LEBANON":
        value = re.sub(r"^\d+[A-Z]?\s+", "", value)
        for word, number in ORDINALS.items():
            value = re.sub(rf"\b{word}\b", number, value)
        value = re.sub(r"\bLEBANON (\d+) WARD\b", r"LEBANON WD \1", value)
        value = value.replace("MOUNT GRETNA", "MT GRETNA")
    if county in {"BERKS", "CUMBERLAND", "LAWRENCE"}:
        value = re.sub(r"\b(READING|CARLISLE|NEW CASTLE|ELLWOOD CITY)(?: BORO)? (\d+)-(\d+)\b", r"\1 WD \2 PCT \3", value)
        value = re.sub(r"\b(READING|CARLISLE|NEW CASTLE|ELLWOOD CITY)(?: BORO)? (\d+)\b", r"\1 WD \2", value)
    return norm(value)


def detailed_norm(value: str) -> str:
    """Disambiguate borough and township labels when both share a place name."""
    value = re.sub(r"\b(TOWNSHIP|TWP)\b", " TOWNSHIP ", value.upper())
    value = re.sub(r"\b(BOROUGH|BORO)\b", " BOROUGH ", value)
    return norm(value) + "|" + ("TOWNSHIP" if "TOWNSHIP" in value else "BOROUGH" if "BOROUGH" in value else "")


def geometry_index() -> dict[str, dict[str, list[str]]]:
    geo = json.loads((ROOT / "data" / "pa_current_voting_districts.geojson").read_text(encoding="utf-8"))
    index: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for feature in geo["features"]:
        props = feature["properties"]
        county = props["county_norm"]
        if county in SOURCES:
            for key in (norm(props["precinct_name"]), detailed_norm(props["precinct_name"])):
                if props["precinct_norm"] not in index[county][key]:
                    index[county][key].append(props["precinct_norm"])
    return index


def extract_electionware(pdf_path: Path, county: str) -> dict[str, list[dict]]:
    precincts: dict[str, list[dict]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        if "OFFICIAL RESULTS" not in first.upper() or "UNOFFICIAL RESULTS" in first.upper():
            raise ValueError(f"Report does not identify official results: {county}")
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            if len(lines) < 5 or "November 3, 2026" not in lines[2]:
                raise ValueError(f"Unexpected page header: {pdf_path.name} page {page.page_number}")
            precinct = lines[3].strip()
            if "GOVERNOR AND LIEUTENANT GOVERNOR" not in "\n".join(lines).upper():
                continue
            start = next(i for i, line in enumerate(lines) if line.upper() == "GOVERNOR AND LIEUTENANT GOVERNOR")
            rows = []
            for line in lines[start + 1:]:
                if line.upper().startswith("WRITE-IN") or line.upper().startswith("REPRESENTATIVE IN CONGRESS"):
                    break
                match = CANDIDATE.match(line)
                if match:
                    party, candidate, votes, election_day, mail, provisional = match.groups()
                    nums = [int(v.replace(",", "")) for v in (votes, election_day, mail, provisional)]
                    if nums[0] != sum(nums[1:]):
                        raise ValueError(f"Vote split mismatch: {county} {precinct} {line}")
                    canonical = {"DEM": "Josh Shapiro", "REP": "Stacy Garrity", "LIB": "Ken Krawchuk"}[party]
                    if canonical.split()[1].upper() not in candidate.upper():
                        raise ValueError(f"Unexpected governor candidate: {county} {precinct} {line}")
                    rows.append(dict(party=party, candidate=canonical, votes=nums[0], election_day=nums[1], mail=nums[2], provisional=nums[3]))
            if {r["party"] for r in rows} != {"DEM", "REP", "LIB"}:
                raise ValueError(f"Missing governor candidates: {county} {precinct} page {page.page_number}")
            if precinct in precincts:
                raise ValueError(f"Duplicate governor precinct: {county} {precinct}")
            precincts[precinct] = rows
    if not precincts:
        raise ValueError(f"No governor precincts found: {county}")
    return precincts


def extract_lycoming(pdf_path: Path) -> dict[str, list[dict]]:
    precincts: dict[str, list[dict]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        if "Official Results by Precinct" not in first:
            raise ValueError("Lycoming report does not identify official results")
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            for i, line in enumerate(lines):
                if not line.startswith("Precinct "):
                    continue
                precinct = line.removeprefix("Precinct ").strip()
                end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("Precinct ")), len(lines))
                block = lines[i + 1:end]
                start = next((j for j, item in enumerate(block) if item.startswith("Governor and Lieutenant Governor")), None)
                if start is None:
                    continue
                candidates = []
                for item in block[start + 1:]:
                    if item.startswith("Total "):
                        break
                    match = re.match(r"^(Josh Shapiro|Stacy Garrity|Ken Krawchuk) ([\d,]+) [\d.]+% ([\d,]+) ([\d,]+) ([\d,]+)$", item)
                    if match:
                        candidate, *numbers = match.groups()
                        votes, day, mail, provisional = [int(v.replace(",", "")) for v in numbers]
                        if votes != day + mail + provisional:
                            raise ValueError(f"Lycoming vote split mismatch: {precinct} {item}")
                        party = {"Josh Shapiro": "DEM", "Stacy Garrity": "REP", "Ken Krawchuk": "LIB"}[candidate]
                        candidates.append(dict(party=party, candidate=candidate, votes=votes, election_day=day, mail=mail, provisional=provisional))
                if {r["party"] for r in candidates} != {"DEM", "REP", "LIB"}:
                    raise ValueError(f"Missing Lycoming candidates: {precinct}")
                if precinct in precincts:
                    raise ValueError(f"Duplicate Lycoming precinct: {precinct}")
                precincts[precinct] = candidates
    if len(precincts) != 80:
        raise ValueError(f"Expected 80 Lycoming precincts, found {len(precincts)}")
    return precincts


def extract_susquehanna(pdf_path: Path) -> dict[str, list[dict]]:
    precincts: dict[str, list[dict]] = {}
    with pdfplumber.open(pdf_path) as pdf:
        first = pdf.pages[0].extract_text() or ""
        if "FINAL CERTIFICATION" not in first:
            raise ValueError("Susquehanna report lacks certification")
        for page in pdf.pages[1:]:
            lines = (page.extract_text() or "").splitlines()
            if "OFFICIAL RESULTS" not in lines or "GOVERNOR AND LT. GOV" not in lines:
                continue
            precinct = lines[6].strip()
            start = lines.index("GOVERNOR AND LT. GOV")
            block = lines[start + 1:]
            candidates = []
            for label, party, candidate in [("JOSH SHAPIRO / AUSTIN DAVIS", "DEM", "Josh Shapiro"), ("STACY GARRITY / JASON", "REP", "Stacy Garrity"), ("KEN KRAWCHUK / JOHN", "LIB", "Ken Krawchuk")]:
                match = next((re.match(rf"^{re.escape(label)} ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)$", line) for line in block if line.startswith(label)), None)
                if not match:
                    raise ValueError(f"Missing Susquehanna candidate: {precinct} {label}")
                votes, day, mail, provisional = [int(v.replace(",", "")) for v in match.groups()]
                if votes != day + mail + provisional:
                    raise ValueError(f"Susquehanna vote split mismatch: {precinct} {label}")
                candidates.append(dict(party=party, candidate=candidate, votes=votes, election_day=day, mail=mail, provisional=provisional))
            if precinct in precincts:
                raise ValueError(f"Duplicate Susquehanna precinct: {precinct}")
            precincts[precinct] = candidates
    if not precincts:
        raise ValueError("No Susquehanna governor precincts found")
    return precincts


def main() -> None:
    index = geometry_index()
    rows = []
    audit = {"status": "official_partial", "election": "2026-11-03 general", "sources": SOURCES, "counties": {}}
    for county in SOURCES:
        pdf_path = PDF_DIR / f"{county.lower()}.pdf"
        precincts = (extract_lycoming(pdf_path) if county == "LYCOMING" else extract_susquehanna(pdf_path) if county == "SUSQUEHANNA" else extract_electionware(pdf_path, county))
        unmatched = []
        matched = 0
        county_votes = defaultdict(int)
        resolved = {}
        for source_name in precincts:
            precise = index[county].get(detailed_norm(source_name), [])
            targets = precise if len(precise) == 1 else index[county].get(source_norm(county, source_name), [])
            resolved[source_name] = targets
        target_counts = defaultdict(int)
        for targets in resolved.values():
            if len(targets) == 1:
                target_counts[targets[0]] += 1
        for source_name, candidates in precincts.items():
            targets = resolved[source_name]
            if len(targets) == 1 and target_counts[targets[0]] == 1:
                output_name = targets[0]
                matched += 1
            else:
                output_name = f"{county} - UNMATCHED {source_name}"
                unmatched.append({"source_precinct": source_name, "normalized": source_norm(county, source_name), "candidate_geometry": targets})
            for candidate in candidates:
                county_votes[candidate["party"]] += candidate["votes"]
                rows.append({"county": county, "precinct": output_name, "office": "Governor", "district": "", **candidate})
        audit["counties"][county] = {"precincts": len(precincts), "matched_precincts": matched, "unmatched_precincts": unmatched, "votes_by_party": dict(county_votes)}
    county_rows = {row["county"]: row for row in json.loads((ROOT / "data" / "contests" / "governor_2026.json").read_text(encoding="utf-8"))["rows"]}
    audit["counties_without_verified_precinct_report"] = sorted(set(county_rows) - set(SOURCES))
    for county, info in audit["counties"].items():
        expected = county_rows[county]
        for party, key in (("DEM", "dem_votes"), ("REP", "rep_votes"), ("LIB", "other_votes")):
            if info["votes_by_party"][party] != expected[key]:
                raise ValueError(f"{county} {party} precinct total differs from current state county total")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    AUDIT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    manifest["years"] = [entry for entry in manifest["years"] if entry["year"] != 2026]
    manifest["years"].append({"year": 2026, "status": "official_partial", "source_type": "county_precinct_pdf", "sources": SOURCES, "output": OUT.relative_to(ROOT).as_posix(), "rows": len(rows), "counties": len(SOURCES), "precincts": sum(x["precincts"] for x in audit["counties"].values()), "matched_precincts": sum(x["matched_precincts"] for x in audit["counties"].values()), "audit": AUDIT.relative_to(ROOT).as_posix()})
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({county: {key: value for key, value in info.items() if key != "unmatched_precincts"} | {"unmatched_count": len(info["unmatched_precincts"])} for county, info in audit["counties"].items()}, indent=2))


if __name__ == "__main__":
    main()

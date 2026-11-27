#!/usr/bin/env python3
"""Extract certified 2026 congressional and legislative precinct vote rows.

This is a partial-county source table for district analysis. It is deliberately
not a statewide district result: uncovered counties and unmatched map precincts
must be resolved before publishing complete district aggregates.
"""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pdfplumber

from import_pa_2026_county_precincts import (
    CANDIDATE, FIELDNAMES, PDF_DIR, ROOT, SOURCES, detailed_norm,
    geometry_index, source_norm,
)


OUT = ROOT / "data" / "Openelections" / "2026" / "20261103__pa__general__district_races_county_official.csv"
AUDIT = ROOT / "data" / "pa_2026_district_races_audit.json"
LYCOMING_PARTIES = {
    "Ray Bilger": "DEM", "Glenn GT Thompson": "REP",
    "Rachel Wallace": "DEM", "Dan Meuser": "REP",
    "Jamie L. Flick": "REP", "Joe Hamm": "REP",
}


def office_heading(line: str, county: str = "") -> tuple[str, str] | None:
    upper = line.upper()
    if "REPRESENTATIVE IN CONGRESS" in upper:
        match = re.search(r"(\d+)(?:ST|ND|RD|TH)?(?: CONGRESSIONAL)? DISTRICT", upper)
        return ("U.S. House", match[1] if match else "16") if match or county == "LAWRENCE" else None
    if "SENATOR IN THE GENERAL ASSEMBLY" in upper:
        match = re.search(r"(?:DISTRICT\s+)?(\d+)(?:ST|ND|RD|TH)?(?: SENATORIAL)?(?: DISTRICT)?", upper)
        return ("State Senate", match[1]) if match else None
    if "REPRESENTATIVE IN THE GENERAL ASSEMBLY" in upper:
        match = re.search(r"(\d+)(?:ST|ND|RD|TH)?(?: LEGISLATIVE)?(?: DISTRICT)?", upper)
        return ("State House", match[1]) if match else None
    return None


def record(office: str, district: str, party: str, candidate: str, values: list[int]) -> dict:
    if values[0] != sum(values[1:]):
        raise ValueError(f"Vote-method totals differ: {office} {district} {candidate} {values}")
    return dict(office=office, district=district, party=party, candidate=candidate, votes=values[0],
                election_day=values[1], mail=values[2], provisional=values[3])


def electionware(path: Path, county: str) -> dict[str, list[dict]]:
    result = defaultdict(list)
    with pdfplumber.open(path) as pdf:
        if "OFFICIAL RESULTS" not in (pdf.pages[0].extract_text() or "").upper():
            raise ValueError(f"{county} report is not marked official")
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            if len(lines) < 4 or "November 3, 2026" not in lines[2]:
                raise ValueError(f"Unexpected {county} page {page.page_number}")
            precinct = lines[3].strip()
            current = None
            for line in lines[4:]:
                heading = office_heading(line, county)
                if heading:
                    current = heading
                    continue
                if not current:
                    continue
                match = CANDIDATE.match(line)
                if match:
                    party, candidate, *numeric = match.groups()
                    if party not in {"DEM", "REP", "LIB", "GRN"}:
                        continue
                    values = [int(value.replace(",", "")) for value in numeric]
                    result[precinct].append(record(*current, party, candidate.title(), values))
                    continue
                write_in = re.match(r"^Write-In Totals ([\d,]+)(?: [\d.]+%)? ([\d,]+) ([\d,]+) ([\d,]+)$", line, re.I)
                if write_in:
                    values = [int(value.replace(",", "")) for value in write_in.groups()]
                    result[precinct].append(record(*current, "WRI", "Write-in", values))
    return result


def lycoming(path: Path) -> dict[str, list[dict]]:
    result = defaultdict(list)
    with pdfplumber.open(path) as pdf:
        if "Official Results by Precinct" not in (pdf.pages[0].extract_text() or ""):
            raise ValueError("Lycoming report is not marked official")
        precinct = ""
        current = None
        for page in pdf.pages:
            for line in (page.extract_text() or "").splitlines():
                if line.startswith("Precinct "):
                    precinct = line.removeprefix("Precinct ").strip()
                    current = None
                    continue
                heading = office_heading(line)
                if heading:
                    current = heading
                    continue
                if not precinct or not current:
                    continue
                match = re.match(r"^(.+?) ([\d,]+) [\d.]+% ([\d,]+) ([\d,]+) ([\d,]+)$", line)
                if not match:
                    continue
                candidate, *numeric = match.groups()
                party = LYCOMING_PARTIES.get(candidate)
                if candidate == "Write-in":
                    party = "WRI"
                if not party:
                    if candidate not in {"Total", "Yes", "No"}:
                        raise ValueError(f"Unknown Lycoming candidate party: {candidate}")
                    continue
                values = [int(value.replace(",", "")) for value in numeric]
                result[precinct].append(record(*current, party, candidate, values))
    return result


def susquehanna(path: Path) -> dict[str, list[dict]]:
    result = defaultdict(list)
    with pdfplumber.open(path) as pdf:
        if "FINAL CERTIFICATION" not in (pdf.pages[0].extract_text() or ""):
            raise ValueError("Susquehanna report lacks certification")
        group_precinct = ""
        for offset, page in enumerate(pdf.pages[1:]):
            lines = (page.extract_text() or "").splitlines()
            if "OFFICIAL RESULTS" not in lines or len(lines) < 8:
                continue
            if offset % 3 == 0:
                group_precinct = lines[6].strip()
            precinct = group_precinct
            current = None
            for line in lines[7:]:
                heading = office_heading(line)
                if heading:
                    current = heading
                    continue
                if not current:
                    continue
                match = re.match(r"^(.+?) \((DEM|REP|LIB|GRN)\) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)$", line)
                if match:
                    candidate, party, *numeric = match.groups()
                    values = [int(value.replace(",", "")) for value in numeric]
                    result[precinct].append(record(*current, party, candidate.title(), values))
                    continue
                write_in = re.match(r"^Write-in ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)$", line, re.I)
                if write_in:
                    values = [int(value.replace(",", "")) for value in write_in.groups()]
                    result[precinct].append(record(*current, "WRI", "Write-in", values))
    return result


def main() -> None:
    index = geometry_index()
    rows = []
    audit = {"status": "official_partial", "sources": SOURCES, "counties": {}}
    for county in SOURCES:
        path = PDF_DIR / f"{county.lower()}.pdf"
        precincts = lycoming(path) if county == "LYCOMING" else susquehanna(path) if county == "SUSQUEHANNA" else electionware(path, county)
        target_by_name = {}
        for name in precincts:
            precise = index[county].get(detailed_norm(name), [])
            target_by_name[name] = precise if len(precise) == 1 else index[county].get(source_norm(county, name), [])
        counts = Counter(targets[0] for targets in target_by_name.values() if len(targets) == 1)
        matches = 0
        contests = defaultdict(lambda: defaultdict(int))
        for name, candidates in precincts.items():
            targets = target_by_name[name]
            matched = len(targets) == 1 and counts[targets[0]] == 1
            output_name = targets[0] if matched else f"{county} - UNMATCHED {name}"
            matches += int(matched)
            for item in candidates:
                contests[f"{item['office']} {item['district']}"][item["party"]] += item["votes"]
                rows.append({"county": county, "precinct": output_name, **item})
        audit["counties"][county] = {"precincts_with_district_races": len(precincts), "matched_precincts": matches,
                                     "rows": sum(map(len, precincts.values())), "contests": contests}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    AUDIT.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    manifest_path = ROOT / "data" / "precinct_returns_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = next((item for item in manifest["years"] if item["year"] == 2026), None)
    if entry is None:
        raise ValueError("Run import_pa_2026_county_precincts.py first")
    entry["district_race_output"] = OUT.relative_to(ROOT).as_posix()
    entry["district_race_rows"] = len(rows)
    entry["district_race_audit"] = AUDIT.relative_to(ROOT).as_posix()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(rows), "counties": {name: {"precincts": value["precincts_with_district_races"],
        "matched": value["matched_precincts"], "contests": len(value["contests"])} for name, value in audit["counties"].items()}}, indent=2))


if __name__ == "__main__":
    main()

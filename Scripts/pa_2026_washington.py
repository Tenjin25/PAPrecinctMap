"""Read Washington County's saved official precinct summary report."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

import pdfplumber


SOURCE = Path(__file__).resolve().parents[1] / "data/source_reports/2026_general/washington.pdf"
CANDIDATE = re.compile(r"^(DEM|REP|LIB|IND) (.+?) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)$")
WRITE_IN = re.compile(r"^Write-In Totals ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)$")


def contest_heading(line: str) -> tuple[str, str] | None:
    if line == "GOVERNOR AND LIEUTENANT GOVERNOR":
        return "Governor", ""
    match = re.fullmatch(r"REPRESENTATIVE IN CONGRESS - (\d+)(?:ST|ND|RD|TH) DISTRICT", line)
    if match:
        return "U.S. House", match[1]
    match = re.fullmatch(r"SENATOR IN THE GENERAL ASSEMBLY - (\d+)(?:ST|ND|RD|TH) DISTRICT", line)
    if match:
        return "State Senate", match[1]
    match = re.fullmatch(r"REPRESENTATIVE IN THE GENERAL ASSEMBLY (\d+)(?:ST|ND|RD|TH) DISTRICT", line)
    if match:
        return "State House", match[1]
    return None


def read_washington() -> dict[str, dict[tuple[str, str], list[dict]]]:
    result = defaultdict(lambda: defaultdict(list))
    seen = set()
    with pdfplumber.open(SOURCE) as pdf:
        if len(pdf.pages) != 468:
            raise ValueError("Unexpected Washington report page count")
        for page in pdf.pages:
            lines = (page.extract_text() or "").splitlines()
            if len(lines) < 5 or "Official Results" not in lines[0] or lines[1] != "2026 General Election" or lines[2] != "November 3, 2026 Washington":
                raise ValueError(f"Unexpected Washington page header: {page.page_number}")
            precinct = lines[3].strip()
            current = None
            for line in lines[4:]:
                heading = contest_heading(line)
                if heading:
                    current = heading
                    continue
                if not current:
                    continue
                match = CANDIDATE.match(line)
                write_in = WRITE_IN.match(line)
                if not match and not write_in:
                    continue
                party, candidate, numbers = (match[1], match[2], match.groups()[2:]) if match else ("WRI", "Write-in", write_in.groups())
                values = [int(value.replace(",", "")) for value in numbers]
                if values[0] != sum(values[1:]):
                    raise ValueError(f"Washington vote split mismatch: {page.page_number} {precinct} {line}")
                key = (precinct, *current, party, candidate)
                if key in seen:
                    raise ValueError(f"Duplicate Washington candidate row: {key}")
                seen.add(key)
                result[precinct][current].append(dict(party=party, candidate=candidate.title(),
                    votes=values[0], election_day=values[1], mail=values[2], provisional=values[3]))
    if not result:
        raise ValueError("No Washington precincts found")
    return result

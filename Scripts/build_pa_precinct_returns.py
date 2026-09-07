"""Build browser-ready Pennsylvania precinct return files.

The atlas frontend uses one precinct-return table for both views:

* county mode aggregates these rows by county; and
* precinct mode keeps the county/precinct rows for map coloring.

This script accepts either the PA Department of State's raw fixed-column CSV
exports or OpenElections' already-standardized CSV files.  Raw PA exports are
parsed through the same normalization logic used by the main data pipeline.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
OUTPUT_ROOT = DATA / "Openelections"
MANIFEST_PATH = DATA / "precinct_returns_manifest.json"
CURRENT_GEOMETRY_PATH = DATA / "pa_current_voting_districts.geojson"
COUNTIES_PATH = DATA / "pa_counties.geojson"
MODERN_CROSSWALK_PATH = DATA / "crosswalks" / "pa_modern_precinct_to_vtd20.csv"
HISTORICAL_CROSSWALK_PATH = DATA / "crosswalks" / "pa_historical_precinct_to_vtd20.csv"
CURRENT_CROSSWALK_PATH = DATA / "crosswalks" / "pa_vtd20_to_current_precinct.csv"
CONTEST_ROOT = DATA / "contests"
PRECINCT_ALIAS_PATH = DATA / "precinct_alias_index.json"

FIELDS = [
    "county",
    "precinct",
    "office",
    "district",
    "party",
    "candidate",
    "votes",
    "election_day",
    "mail",
    "provisional",
]

# Official PA bulk exports take precedence over partial/community files.
OFFICIAL_SOURCES = {
    2008: DATA / "ElectionReturns_2008_General_PrecinctReturns.txt",
    2020: DATA / "ElectionReturns_2020_General_PrecinctReturns.txt",
    2022: DATA / "ElectionReturns_2022_General_PrecinctReturns.txt",
    2024: DATA / "erstat_2024_g_268768_20250129.txt",
}

TARGETS = {
    2000: "20001107__pa__general__precinct.csv",
    2004: "20041102__pa__general__precinct.csv",
    2008: "20081104__pa__general__precinct.csv",
    2012: "20121106__pa__general__precinct.csv",
    2016: "20161108__pa__general__precinct.csv",
    2020: "20201103__pa__general__precinct.csv",
    2022: "20221108__pa__general__precinct.csv",
    2024: "20241105__pa__general__precinct_official.csv",
}

# Source labels that are unmatched in their own-year crosswalk but have a
# direct block-derived match in an adjacent-year RDH crosswalk.
BLOCK_FALLBACKS = {
    ("079", "HAZLE DISTRICT 1"): [
        ("079", "000806", 0.178627553693),
        ("079", "000807", 0.821372446307),
    ],
    ("091", "FRANCONIA PRECINCT 2"): [
        ("091", "000915", 0.009714632665),
        ("091", "000918", 0.990285367335),
    ],
    ("091", "HORSHAM DISTRICT 4 DISTRICT 2"): [
        ("091", "001143", 0.717573221757),
        ("091", "001144", 0.282426778243),
    ],
    ("095", "LOWER MOUNT BETHEL D INDEPENDENT"): [
        ("095", "000750", 1.0),
    ],
    ("095", "LOWER MOUNT BETHEL DISTRICT INDEPENDENT"): [
        ("095", "000750", 1.0),
    ],
    ("091", "UPPER MERION DISTRICT GULPH DISTRICT 02"): [
        ("091", "003350", 1.0),
    ],
    ("091", "UPPER MERION X GULPH X 02"): [
        ("091", "003350", 1.0),
    ],
    ("091", "UPPER MERION GULPH 02"): [("091", "003350", 1.0)],
    # Congressional fragments of precincts that are single current VTDs.
    ("031", "PINEY P B (CONG 5)"): [("031", "000340", 1.0)],
    ("031", "PINEY PRECINCT A (CONG 3)"): [("031", "000340", 1.0)],
    ("031", "PINEY PRECINCT B (CONG 5)"): [("031", "000340", 1.0)],
    ("097", "RIVERSIDE P B (CONG 11)"): [("097", "000560", 1.0)],
    ("097", "RIVERSIDE PRECINCT A (CONG 10)"): [("097", "000560", 1.0)],
    ("097", "RIVERSIDE PRECINCT B (CONG 11)"): [("097", "000560", 1.0)],
    ("117", "SHIPPEN P B (CONG 10)"): [("117", "000350", 1.0)],
    ("117", "SHIPPEN PRECINCT A (CONG 5)"): [("117", "000350", 1.0)],
    ("117", "SHIPPEN PRECINCT B (CONG 10)"): [("117", "000350", 1.0)],
    # Historical labels that differ from a uniquely identifiable current VTD.
    ("007", "BEAVER WARD 3-1"): [("007", "000310", 1.0)],
    ("007", "NORTH SEWICKLEY 04 ELLWOOD CITY BOROUGH"): [("007", "001320", 1.0)],
    ("017", "TINICUM TINICM"): [("017", "002400", 1.0)],
    ("021", "JOHNSTOWN WARD 11"): [("021", "000942", 1.0)],
    ("029", "PHOENIXVILLE WARD MIDDLE-1"): [("029", "000917", 1.0)],
    ("043", "SUSQUEHANNA WARD 1 (WARD 4)"): [("043", "001135", 1.0)],
    ("071", "MANOR MANOR,NEW"): [("071", "001402", 1.0)],
    ("073", "NEW BEAVER PRECINCT 1"): [("073", "000255", 1.0)],
    ("095", "LEHIGH DISTRICT PENN"): [("095", "000730", 1.0)],
    ("029", "KENNETT PRECINCT 2 A (CONG 7)"): [("029", "000610", 1.0)],
    ("029", "KENNETT PRECINCT 2 B (CONG 16)"): [("029", "000610", 1.0)],
    ("091", "LOWER MERION WARD 2-2 A (CONG 2)"): [("091", "001430", 1.0)],
    ("091", "LOWER MERION WARD 2-2 B (CONG 13)"): [("091", "001430", 1.0)],
    ("091", "PLYMOUTH 2 3A (CONG 7)"): [("091", "002488", 1.0)],
    ("091", "PLYMOUTH 2 3B (CONG 13)"): [("091", "002488", 1.0)],
    ("091", "HATFIELD 5 2 A (CONG 13)"): [("091", "001036", 1.0)],
    ("091", "HATFIELD 5 2 B (CONG 8)"): [("091", "001036", 1.0)],
    ("125", "FALLOWFIELD 2 A (CONG 9)"): [("125", "000910", 1.0)],
    ("125", "FALLOWFIELD 2 B (CONG 18)"): [("125", "000910", 1.0)],
    ("071", "MANHEIM DISTRICT 7:00 AM"): [("071", "001200", 1.0)],
    ("075", "NORTH LEBANON EAST A (CONG 6)"): [("075", "000350", 1.0)],
    ("075", "NORTH LEBANON EAST B (CONG 15)"): [("075", "000350", 1.0)],
    ("091", "HORSHAM 2 2 A (CONG 7)"): [("091", "001085", 1.0)],
    ("091", "HORSHAM 2 2 B (CONG 13)"): [("091", "001085", 1.0)],
    ("045", "SPRINGFIELD WARD 3-02(161)"): [("045", "002810", 1.0)],
    ("045", "SPRINGFIELD WARD 3-02(165)"): [("045", "002820", 1.0)],
    ("089", "EAST STROUDSBURG DISTRICT 1-11TH CONGRESSIONAL"): [("089", "000070", 1.0)],
    ("089", "EAST STROUDSBURG DISTRICT 3-10TH CONGRESSIONAL"): [("089", "000090", 1.0)],
    ("089", "EAST STROUDSBURG DISTRICT 4-11TH CONGRESSIONAL"): [("089", "000100", 1.0)],
    ("089", "EAST STROUDSBURG DISTRICT 5-11TH CONGRESSIONAL"): [("089", "000110", 1.0)],
    # Legacy subprecincts that consolidate into uniquely identifiable current VTDs.
    ("027", "FERGUSON NORTHEAST 1A"): [("027", "000205", 1.0)],
    ("027", "FERGUSON NORTHEAST 1B"): [("027", "000205", 1.0)],
    ("027", "FERGUSON NORTH CENTRAL 2"): [("027", "000200", 1.0)],
    ("027", "FERGUSON WEST CENTRAL 1"): [("027", "000230", 1.0)],
    ("061", "PENN PRECINCT A (5TH CONG)"): [("061", "000380", 1.0)],
    ("061", "PENN PRECINCT B (9TH CONG)"): [("061", "000380", 1.0)],
    ("091", "WHITPAIN 02 92"): [("091", "003860", 1.0)],
    ("091", "WHITPAIN 03 92"): [("091", "003821", 1.0)],
    ("091", "WHITPAIN 04 92"): [("091", "003825", 1.0)],
    ("091", "WHITPAIN 05 92"): [("091", "003831", 1.0)],
    ("091", "WHITPAIN 06 92"): [("091", "003835", 1.0)],
    ("101", "PHILADELPHIA WARD 40-30 A (SENATE 1)"): [("101", "004030", 1.0)],
    ("101", "PHILADELPHIA WARD 40-30 B (SENATE 8)"): [("101", "004030", 1.0)],
    # Both historical subprecincts were consolidated into one current VTD.
    ("045", "NETHER PROVIDENCE W 3 D 2"): [
        ("045", "002061", 1.0),
    ],
    ("095", "BETHLEHEM TOWNSHIP W 2 D 3"): [
        ("095", "000339", 1.0),
    ],
}


def load_pipeline_helpers():
    # Import lazily so --help works even when optional geospatial dependencies
    # used by the larger build are not installed.
    import sys

    sys.path.insert(0, str(BASE))
    import build_pa_data_layers as pipeline

    return pipeline


def canonical_rows(source: Path, year: int) -> list[dict[str, str]]:
    pipeline = load_pipeline_helpers()
    with source.open("r", encoding="utf-8-sig", errors="ignore") as handle:
        text = handle.read()
    raw_source = text.splitlines() and not text.splitlines()[0].lower().startswith("county,")
    rows = pipeline.read_csv_rows(source)
    source_precincts = []
    if raw_source:
        raw_rows = list(csv.reader(text.splitlines()))
        valid_offices = set(getattr(pipeline, "RAW_OFFICE_CODE_MAP", {}))
        summary_candidates = {"CAST VOTES", "OVER VOTES", "UNDER VOTES", "TOTAL VOTES"}
        raw_rows = [
            parts for parts in raw_rows
            if len(parts) >= 29
            and str(parts[8]).strip().upper() in valid_offices
            and " ".join(part for part in [parts[12], parts[13], parts[11], parts[14]] if part).strip().upper() not in summary_candidates
        ]
        source_precincts = [
            ((parts[28] if len(parts) >= 29 and str(parts[28]).strip() else "") if year < 2018 else "")
            or " ".join(part for part in parts[(22 if len(parts) >= 35 else 20):(27 if len(parts) >= 35 else 25)] if part).strip()
            for parts in raw_rows
            if parts
        ]
    raw_index = 0
    output = []
    for row in rows:
        county = str(row.get("county") or "").strip()
        precinct = str(row.get("precinct") or "").strip()
        office = str(row.get("office") or "").strip()
        candidate = str(row.get("candidate") or "").strip()
        if not county or not precinct or not office or not candidate:
            continue
        source_precinct = str(row.get("precinct") or "").strip()
        if raw_source:
            # read_csv_rows and read_raw_precinct_rows discard the same invalid
            # rows, but summary rows can differ; advance until the raw source
            # county/precinct pair agrees with the normalized row when possible.
            while raw_index < len(source_precincts) and not source_precincts[raw_index]:
                raw_index += 1
            if raw_index < len(source_precincts):
                source_precinct = source_precincts[raw_index]
                raw_index += 1
        output.append({
            "county": county,
            "precinct": precinct,
            "office": office,
            "district": str(row.get("district") or "").strip(),
            "party": str(row.get("party") or "").strip(),
            "candidate": candidate,
            "votes": str(row.get("votes") or "").strip(),
            "election_day": str(row.get("election_day") or "").strip(),
            "mail": str(row.get("mail") or row.get("early_voting") or "").strip(),
            "provisional": str(row.get("provisional") or "").strip(),
            "source_precinct": source_precinct,
        })
    return output


def normalize_token(value: object) -> str:
    return " ".join(str(value or "").upper().replace("_", " ").split())


def contest_type_from_office(value: object) -> str:
    label = re.sub(r"[^A-Z0-9]+", " ", normalize_token(value)).strip()
    if "PRESIDENT" in label:
        return "president"
    if "UNITED STATES SENATOR" in label or label in {"US SENATE", "U S SENATOR"}:
        return "us_senate"
    if "LIEUTENANT GOVERNOR" in label:
        return "lieutenant_governor"
    if "GOVERNOR" in label:
        return "governor"
    if "ATTORNEY GENERAL" in label:
        return "attorney_general"
    if "TREASURER" in label:
        return "treasurer"
    if "AUDITOR GENERAL" in label or label == "AUDITOR":
        return "auditor"
    return ""


def load_canonical_candidates(year: int) -> dict[tuple[str, str], str]:
    """Use the county-layer candidate spelling as the precinct-layer authority."""
    result = {}
    for path in CONTEST_ROOT.glob(f"*_{year}.json"):
        contest_type = path.stem[: -(len(str(year)) + 1)]
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in payload.get("rows") or []:
            dem = str(row.get("dem_candidate") or "").strip()
            rep = str(row.get("rep_candidate") or "").strip()
            if dem:
                result[(contest_type, "dem")] = dem
            if rep:
                result[(contest_type, "rep")] = rep
            if dem and rep:
                break
    return result


def align_candidate_names(rows: list[dict[str, str]], year: int) -> None:
    canonical = load_canonical_candidates(year)
    for row in rows:
        contest_type = contest_type_from_office(row.get("office"))
        party = normalize_token(row.get("party"))
        party_bucket = "dem" if party.startswith("DEM") else ("rep" if party.startswith("REP") else "")
        candidate = canonical.get((contest_type, party_bucket))
        if candidate:
            row["candidate"] = candidate


def source_variants(value: object) -> list[str]:
    """Match PA export abbreviations to crosswalk labels."""
    base = normalize_token(value)
    if not base:
        return []
    variants = []
    queue = [base]
    replacements = (
        (r"\bD\s+(\d+)\b", r"DISTRICT \1"),
        (r"\bX\s+(\d+)\b", r"DISTRICT \1"),
        (r"\bWD\s+(\d+)\b", r"WARD \1"),
        (r"\bW\s+(\d+)\b", r"WARD \1"),
        (r"\bPCT\s+(\d+)\b", r"PRECINCT \1"),
        (r"\bP\s+(\d+)\b", r"PRECINCT \1"),
        (r"\bTWP\b", "TOWNSHIP"),
        (r"\bBORO\b", "BOROUGH"),
    )
    seen = set()
    while queue:
        candidate = normalize_token(queue.pop())
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        variants.append(candidate)
        expanded_mount = re.sub(r"\bMT\.?", "MOUNT", candidate)
        if expanded_mount != candidate:
            queue.append(expanded_mount)
        unpadded_numbers = re.sub(r"\b0+(\d+)\b", r"\1", candidate)
        if unpadded_numbers != candidate:
            queue.append(unpadded_numbers)
        without_district_note = re.sub(
            r"(?:\s+[AB])?\s*\([^)]*(?:CONG|CONGRESSIONAL|USC|SENATE|STH)[^)]*\)",
            "",
            candidate,
        )
        without_district_note = re.sub(
            r"[-\s]+\d+(?:ST|ND|RD|TH)?\s+CONGRESSIONAL$",
            "",
            without_district_note,
        )
        without_district_note = re.sub(r"\s*\(\d+\)$", "", without_district_note)
        if without_district_note != candidate:
            queue.append(without_district_note)
        without_split_suffix = re.sub(r"(?<=\d)\s*[AB]$", "", candidate)
        if without_split_suffix != candidate:
            queue.append(without_split_suffix)
        tokens = candidate.split()
        # PA's raw exports sometimes repeat the ward/district suffix, e.g.
        # "CARLISLE W 1 P 1 W 1 P 1".
        for width in range(1, len(tokens) // 2 + 1):
            if tokens[-2 * width:-width] == tokens[-width:]:
                queue.append(" ".join(tokens[:-width]))
                break
        for pattern, replacement in replacements:
            expanded = re.sub(pattern, replacement, candidate)
            if expanded != candidate:
                queue.append(expanded)
    return variants


def load_county_fips() -> dict[str, str]:
    payload = json.loads(COUNTIES_PATH.read_text(encoding="utf-8"))
    result = {}
    for feature in payload.get("features", []):
        props = feature.get("properties") or {}
        fips = str(props.get("COUNTYFP20") or props.get("COUNTYFP") or "").zfill(3)
        name = normalize_token(props.get("NAME20") or props.get("NAME"))
        if fips and name:
            result[name] = fips
    return result


def load_crosswalk(year: int, county_fips_by_name: dict[str, str]) -> dict[tuple[str, str], list[tuple[str, str, float]]]:
    path = HISTORICAL_CROSSWALK_PATH if year < 2018 else MODERN_CROSSWALK_PATH
    index: dict[tuple[str, str], list[tuple[str, str, float]]] = {}
    if not path.exists():
        return index
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            if int(row.get("year") or 0) != year or not row.get("dst_vtd"):
                continue
            county = str(row.get("countyfp") or "").zfill(3)
            sources = source_variants(row.get("source_precinct"))
            dst_county = str(row.get("dst_countyfp") or county).zfill(3)
            dst_vtd = str(row.get("dst_vtd") or "").strip().zfill(6)
            weight = float(row.get("weight") or 0)
            if county and sources and dst_vtd and weight > 0:
                for source in sources:
                    index.setdefault((county, source), []).append((dst_county, dst_vtd, weight))
    return index


def load_current_crosswalk() -> dict[tuple[str, str], list[tuple[str, str, str, float]]]:
    """Map legacy VTD20 targets into the precinct polygons used by the frontend."""
    index: dict[tuple[str, str], list[tuple[str, str, str, float]]] = {}
    if not CURRENT_CROSSWALK_PATH.exists():
        return index
    with CURRENT_CROSSWALK_PATH.open("r", newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            county = str(row.get("countyfp") or "").zfill(3)
            vtd20 = str(row.get("vtd20") or "").zfill(6)
            current_county = str(row.get("current_countyfp") or county).zfill(3)
            current_vtd = str(row.get("current_vtd") or "").zfill(6)
            current_precinct = normalize_token(row.get("current_precinct_norm"))
            weight = float(row.get("weight") or 0)
            if county and vtd20 and current_vtd and current_precinct and weight > 0:
                index.setdefault((county, vtd20), []).append(
                    (current_county, current_vtd, current_precinct, weight)
                )
    return index


def load_current_vtd_keys() -> set[tuple[str, str]]:
    """Return county/VTD IDs that are actually present in the frontend layer."""
    try:
        payload = json.loads(CURRENT_GEOMETRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    keys = set()
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        county = str(props.get("COUNTYFP") or props.get("COUNTY") or "").zfill(3)
        vtd = str(props.get("VTD") or props.get("VTDST") or "").zfill(6)
        if county and vtd and vtd != "000000":
            keys.add((county, vtd))
    return keys


def load_current_name_crosswalk() -> dict[tuple[str, str], tuple[str, str]]:
    """Return unambiguous county/name aliases for current geometry precincts."""
    try:
        payload = json.loads(CURRENT_GEOMETRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    candidates: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for feature in payload.get("features") or []:
        props = feature.get("properties") or {}
        county = str(props.get("COUNTYFP") or props.get("COUNTY") or "").zfill(3)
        vtd = str(props.get("VTD") or props.get("VTDST") or "").zfill(6)
        precinct = normalize_token(props.get("precinct_norm"))
        name = props.get("precinct_name") or props.get("NAME")
        if not county or not vtd or not precinct or not name:
            continue
        for alias in source_variants(name):
            candidates.setdefault((county, alias), set()).add((vtd, precinct))
    return {key: next(iter(values)) for key, values in candidates.items() if len(values) == 1}


def load_unambiguous_precinct_aliases(
    county_fips_by_name: dict[str, str],
) -> dict[tuple[str, str], str]:
    """Map unique historical name aliases to a single VTD identifier."""
    try:
        payload = json.loads(PRECINCT_ALIAS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result = {}
    for county_name, aliases in (payload.get("counties") or {}).items():
        county = county_fips_by_name.get(normalize_token(county_name))
        if not county:
            continue
        for alias, values in (aliases or {}).items():
            unique = {str(value).strip().upper().zfill(6) for value in values if str(value).strip()}
            if len(unique) == 1:
                result[(county, normalize_token(alias))] = next(iter(unique))
    return result


def load_neighbor_year_crosswalk(year: int) -> dict[tuple[str, str], list[tuple[str, str, float]]]:
    """Use the closest other-year mapping for the exact same precinct label."""
    grouped: dict[tuple[int, str, str], list[tuple[str, str, float]]] = {}
    for path in (HISTORICAL_CROSSWALK_PATH, MODERN_CROSSWALK_PATH):
        if not path.exists():
            continue
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                ref_year = int(row.get("year") or 0)
                dst_vtd = str(row.get("dst_vtd") or "").strip().upper().zfill(6)
                weight = float(row.get("weight") or 0)
                if ref_year == year or not dst_vtd or weight <= 0:
                    continue
                county = str(row.get("countyfp") or "").zfill(3)
                label = normalize_token(row.get("source_precinct"))
                dst_county = str(row.get("dst_countyfp") or county).zfill(3)
                grouped.setdefault((ref_year, county, label), []).append((dst_county, dst_vtd, weight))
    choices: dict[tuple[str, str], list[tuple[int, list[tuple[str, str, float]]]]] = {}
    for (ref_year, county, label), targets in grouped.items():
        choices.setdefault((county, label), []).append((ref_year, targets))
    result = {}
    for key, options in choices.items():
        # Prefer the closest year; on a tie, prefer the later boundary vintage.
        _, targets = min(options, key=lambda item: (abs(item[0] - year), item[0] < year))
        total = sum(weight for _, _, weight in targets) or 1.0
        result[key] = [(county, vtd, weight / total) for county, vtd, weight in targets]
    return result


def join_to_current_vtds(year: int, rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict]:
    county_fips_by_name = load_county_fips()
    county_names_by_fips = {v: k for k, v in county_fips_by_name.items()}
    crosswalk = load_crosswalk(year, county_fips_by_name)
    current_crosswalk = load_current_crosswalk()
    current_vtd_keys = load_current_vtd_keys()
    current_name_crosswalk = load_current_name_crosswalk()
    precinct_aliases = load_unambiguous_precinct_aliases(county_fips_by_name)
    neighbor_crosswalk = load_neighbor_year_crosswalk(year)
    joined = []
    matched_rows = 0
    unmatched_rows = 0
    for row in rows:
        county = normalize_token(row["county"])
        county_fips = county_fips_by_name.get(county, "")
        source = normalize_token(row.get("source_precinct") or row["precinct"])
        if source.isdigit() and not int(source):
            source = normalize_token(row["precinct"])
        canonical = re.match(r"^(.+?)\s+-\s+([A-Z0-9]{6,})$", source)
        if canonical and normalize_token(canonical.group(1)) == county:
            source = canonical.group(2)
        if year < 2018 and source.isdigit():
            source = source.zfill(6)
        targets = []
        source_code = source.zfill(6)
        if (county_fips, source_code) in current_vtd_keys or (county_fips, source_code) in current_crosswalk:
            targets = [(county_fips, source_code, 1.0)]
        for variant in source_variants(source):
            if targets:
                break
            targets = crosswalk.get((county_fips, variant), [])
            if targets:
                break
        if not targets:
            for variant in source_variants(row.get("precinct")) + source_variants(source):
                targets = BLOCK_FALLBACKS.get((county_fips, variant), [])
                if targets:
                    break
        if not targets:
            for variant in source_variants(row.get("precinct")) + source_variants(source):
                targets = neighbor_crosswalk.get((county_fips, variant), [])
                if targets:
                    break
        if not targets:
            for variant in source_variants(row.get("precinct")) + source_variants(source):
                alias_vtd = precinct_aliases.get((county_fips, variant))
                if alias_vtd and (county_fips, alias_vtd) in current_crosswalk:
                    targets = [(county_fips, alias_vtd, 1.0)]
                    break
        if not targets:
            for alias in source_variants(row.get("precinct")) + source_variants(source):
                named_target = current_name_crosswalk.get((county_fips, alias))
                if named_target:
                    _, named_precinct = named_target
                    joined.append({
                        **row,
                        "county": county,
                        "precinct": named_precinct,
                        "source_precinct": source,
                    })
                    matched_rows += 1
                    break
            else:
                named_target = None
            if named_target:
                continue
        if not targets:
            unmatched_rows += 1
            joined.append({**row, "precinct": row["precinct"], "source_precinct": source})
            continue
        matched_rows += 1
        for dst_county, dst_vtd, weight in targets:
            current_targets = current_crosswalk.get((dst_county, dst_vtd))
            # Some county-specific modern exceptions store the state's local
            # code (for example Allegheny F411 or Cumberland 620), rather than
            # a Census VTD20 code. Resolve it to the namespaced current key.
            if not current_targets:
                local_code = dst_vtd.lstrip("0").zfill(3)
                local_current_vtd = f"{dst_county}{local_code}"
                if (dst_county, local_current_vtd) in current_vtd_keys:
                    current_targets = [(
                        dst_county,
                        local_current_vtd,
                        f"{county_names_by_fips.get(dst_county, county)} - {local_current_vtd}",
                        1.0,
                    )]
            if not current_targets and dst_county == county_fips:
                for alias in source_variants(row.get("precinct")) + source_variants(source):
                    named_target = current_name_crosswalk.get((dst_county, alias))
                    if named_target:
                        named_vtd, named_precinct = named_target
                        current_targets = [(dst_county, named_vtd, named_precinct, 1.0)]
                        break
            if not current_targets:
                current_targets = [(dst_county, dst_vtd, f"{county_names_by_fips.get(dst_county, county)} - {dst_vtd}", 1.0)]
            for current_county, current_vtd, current_precinct, current_weight in current_targets:
                votes = float(row.get("votes") or 0) * weight * current_weight
                target_county = county_names_by_fips.get(current_county, county)
                joined.append({
                    **row,
                    "county": target_county,
                    "precinct": current_precinct,
                    "votes": f"{votes:.12f}".rstrip("0").rstrip("."),
                    "source_precinct": source,
                })
    return joined, {
        "crosswalk": str((HISTORICAL_CROSSWALK_PATH if year < 2018 else MODERN_CROSSWALK_PATH).relative_to(BASE)).replace("\\", "/"),
        "current_crosswalk": str(CURRENT_CROSSWALK_PATH.relative_to(BASE)).replace("\\", "/"),
        "matched_rows": matched_rows,
        "unmatched_rows": unmatched_rows,
        "joined_rows": len(joined),
    }


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(temp, path)


def is_standardized(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8-sig", errors="ignore") as handle:
            header = handle.readline().strip().lower()
        return header.startswith("county,precinct,office,")
    except OSError:
        return False


def choose_source(year: int) -> tuple[Path | None, str]:
    official = OFFICIAL_SOURCES.get(year)
    if official and official.exists():
        return official, "official_pa_precinct_export"

    target = OUTPUT_ROOT / str(year) / TARGETS[year]
    raw_backup = target.with_suffix(target.suffix + ".raw")
    if year < 2018 and raw_backup.exists():
        return raw_backup, "openelections_raw_export"
    preserved_source = target.with_suffix(target.suffix + ".source")
    if preserved_source.exists():
        return preserved_source, "preserved_standardized_source"

    if target.exists():
        return target, "openelections_or_existing_standardized"

    if raw_backup.exists():
        return raw_backup, "openelections_raw_export"
    return None, "missing"


def current_geometry_metadata() -> dict:
    """Describe the geometry actually loaded by the frontend."""
    try:
        payload = json.loads(CURRENT_GEOMETRY_PATH.read_text(encoding="utf-8"))
        features = payload.get("features") or []
        with_norm = sum(1 for feature in features if (feature.get("properties") or {}).get("precinct_norm"))
        return {
            "source": str(CURRENT_GEOMETRY_PATH.relative_to(BASE)).replace("\\", "/"),
            "features": len(features),
            "features_with_precinct_norm": with_norm,
        }
    except (OSError, json.JSONDecodeError):
        return {"source": str(CURRENT_GEOMETRY_PATH.relative_to(BASE)).replace("\\", "/"), "features": 0, "features_with_precinct_norm": 0}


def build_year(year: int, force: bool = False) -> dict:
    target_name = TARGETS[year]
    source, source_type = choose_source(year)
    target = OUTPUT_ROOT / str(year) / target_name
    if source is None:
        return {
            "year": year,
            "status": "missing",
            "source": "",
            "rows": 0,
            "counties": 0,
            "precincts": 0,
        }

    reuse_existing = target.exists() and is_standardized(target) and not force
    if reuse_existing:
        rows = canonical_rows(target, year)
        source_type = "existing_standardized"
    else:
        rows = canonical_rows(source, year)
    align_candidate_names(rows, year)
    rows, crosswalk_meta = join_to_current_vtds(year, rows)
    for row in rows:
        row.pop("source_precinct", None)
    if not reuse_existing:
        write_rows(target, rows)
    counties = {row["county"].upper() for row in rows}
    precincts = {(row["county"].upper(), row["precinct"].upper()) for row in rows}
    return {
        "year": year,
        "status": "built",
        "source": str(source.relative_to(BASE)).replace("\\", "/"),
        "source_type": source_type,
        "output": str(target.relative_to(BASE)).replace("\\", "/"),
        "rows": len(rows),
        "counties": len(counties),
        "precincts": len(precincts),
        **crosswalk_meta,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        default=sorted(TARGETS),
        help="Election years to build; defaults to all configured years.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rewrite standardized outputs even when they already exist.",
    )
    args = parser.parse_args()

    unknown = sorted(set(args.years) - set(TARGETS))
    if unknown:
        parser.error(f"unsupported year(s): {', '.join(map(str, unknown))}")

    built_results = [build_year(year, force=args.force) for year in sorted(set(args.years))]
    results = built_results
    # A targeted rebuild must not erase metadata for the other configured years.
    if set(args.years) != set(TARGETS) and MANIFEST_PATH.exists():
        try:
            existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            by_year = {entry["year"]: entry for entry in existing.get("years", [])}
            by_year.update({entry["year"]: entry for entry in results})
            results = [by_year[year] for year in sorted(by_year)]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
    MANIFEST_PATH.write_text(
        json.dumps({
            "generated_by": Path(__file__).name,
            "frontend_geometry": current_geometry_metadata(),
            "years": results,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    for result in built_results:
        print(
            f"{result['year']}: {result['status']} "
            f"{result['rows']:,} rows, {result['counties']} counties, "
            f"{result['precincts']:,} precincts"
        )


if __name__ == "__main__":
    main()

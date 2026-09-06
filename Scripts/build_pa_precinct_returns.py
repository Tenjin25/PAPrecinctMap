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
    )
    seen = set()
    while queue:
        candidate = normalize_token(queue.pop())
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        variants.append(candidate)
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


def join_to_current_vtds(year: int, rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict]:
    county_fips_by_name = load_county_fips()
    county_names_by_fips = {v: k for k, v in county_fips_by_name.items()}
    crosswalk = load_crosswalk(year, county_fips_by_name)
    current_crosswalk = load_current_crosswalk()
    current_vtd_keys = load_current_vtd_keys()
    joined = []
    matched_rows = 0
    unmatched_rows = 0
    for row in rows:
        county = normalize_token(row["county"])
        county_fips = county_fips_by_name.get(county, "")
        source = normalize_token(row.get("source_precinct") or row["precinct"])
        canonical = re.match(r"^(.+?)\s+-\s+([A-Z0-9]{6,})$", source)
        if canonical and normalize_token(canonical.group(1)) == county:
            joined.append({**row, "county": county, "precinct": f"{county} - {canonical.group(2)}", "source_precinct": source})
            matched_rows += 1
            continue
        if year < 2018 and source.isdigit():
            source = source.zfill(6)
        targets = []
        if source.isdigit() and (county_fips, source.zfill(6)) in current_vtd_keys:
            targets = [(county_fips, source.zfill(6), 1.0)]
        for variant in source_variants(source):
            if targets:
                break
            targets = crosswalk.get((county_fips, variant), [])
            if targets:
                break
        if not targets:
            unmatched_rows += 1
            joined.append({**row, "precinct": row["precinct"], "source_precinct": source})
            continue
        matched_rows += 1
        for dst_county, dst_vtd, weight in targets:
            current_targets = current_crosswalk.get((dst_county, dst_vtd))
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

    results = [build_year(year, force=args.force) for year in sorted(set(args.years))]
    MANIFEST_PATH.write_text(
        json.dumps({
            "generated_by": Path(__file__).name,
            "frontend_geometry": current_geometry_metadata(),
            "years": results,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    for result in results:
        print(
            f"{result['year']}: {result['status']} "
            f"{result['rows']:,} rows, {result['counties']} counties, "
            f"{result['precincts']:,} precincts"
        )


if __name__ == "__main__":
    main()

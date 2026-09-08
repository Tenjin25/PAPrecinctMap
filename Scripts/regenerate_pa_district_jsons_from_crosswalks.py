"""Regenerate PA district contest JSONs from precinct returns and block chains.

The allocation path is:

    raw precinct votes -> source VTD -> weighted VTD20 chain
    -> area-weighted VTD20 legislative district -> district result JSON

This intentionally writes to a separate directory by default.  Use --out-dir
data/district_contests to replace the application's normal district slices.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import zipfile
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CROSSWALKS = DATA / "crosswalks"
CRS = "EPSG:5070"

SCOPES = {
    "congressional": ("pa_block20_to_congressional_2022.csv", "pa_congressional_districts.csv"),
    "state_house": ("pa_block20_to_state_house_2022.csv", "pa_state_house_districts.csv"),
    "state_senate": ("pa_block20_to_state_senate_2022.csv", "pa_state_senate_districts.csv"),
}

VTD_CHAIN_CACHE = {}
HISTORICAL_PRECINCT_CROSSWALK_CACHE = {}
MODERN_PRECINCT_CROSSWALK_CACHE = {}
VTD_MEMBERSHIP_CACHE = {}
VTD_ALIAS_CACHE = {}
PROXY_ALIAS_CACHE = None
HISTORICAL_GEOMETRY_CACHE = {}
CURRENT_ALIAS_PREFIX_CACHE = {}
LIVE_VTD_CROSSWALK_CACHE = None
LIVE_ALIAS_CACHE = None
LIVE_SIMPLE_ALIAS_CACHE = None
LIVE_DISTRICT_CACHE = {}
LIVE_TARGET_CACHE = {}

# Chester County's 2006-era precinct maps confirm these two precincts, but
# the Census 2000 VTD layer omits them. These targets were calculated by
# intersecting the 2011 county polygons with tabblock00, then carrying those
# blocks through the existing 2000->2010->2020 bridge.
CHESTER_TABBLOCK_PROXY_TARGETS = {
    ("029", "000347", "EAST GOSHEN P 09"): [
        ("029", "000295", 0.956937),
        ("029", "000347", 0.043063),
    ],
    ("029", "001465", "WEST BRADFORD P 5"): [
        ("029", "001465", 0.998842),
        ("029", "000770", 0.001158),
    ],
}

# The official PA Department of State 2006 precinct-return file records the
# legacy MCD/precinct codes.  The local 2011 boundary package shows that
# three split precincts were renumbered by 2011; these are code-preserving
# name/code transitions, not spatial guesses.
PA_2006_GEOMETRY_CODE_ALIASES = {
    ("045", "000840"): "000835",  # Concord Southcentral
    ("091", "002497"): "002495",  # Plymouth 2-3C
    ("091", "003085"): "003082",  # Upper Dublin 3-1B
}

# High-confidence 2008 precinct-to-2010 VTD successors. These cover explicit
# renames and code transitions only; consolidated or spatially ambiguous
# precincts remain unmatched and are reported for review.
PA_2008_VTD10_PROXY_ALIASES = {
    ("003", "F150", "SHALER W 3 D 1"): "F142",
    ("011", "000000", "CAERNARVON P 2"): "000195",
    ("011", "000000", "FLEETWOOD D 2"): "400A",
    ("011", "000000", "ROCKLAND P 2"): "1140B",
    ("021", "001330", "NANTY GLO W 2 X 2"): "PR164",
    ("049", "000000", "MILLCREEK D 24"): "PR155",
    ("055", "000000", "SOUTHAMPTON X EAST"): "000551",
    ("071", "001352", "MANHEIM D 20"): "PR245",
    ("071", "001353", "MANHEIM D 21"): "PR243",
    ("071", "001354", "MANHEIM D 22"): "PR244",
    ("071", "001578", "NEW HOLLAND X 3"): "PR248",
    ("091", "002495", "PLYMOUTH X 2 X 3B"): "002490",
    ("091", "002497", "PLYMOUTH X 2 X 3C"): "002490",
    ("091", "000000", "POTTSTOWN X 7 X 1"): "PR415",
    ("091", "000000", "POTTSTOWN X 7 X 2"): "PR416",
    ("091", "000000", "SKIPPACK X 3"): "PR417",
    ("091", "003085", "UPPER DUBLIN X 3 X 1B"): "003080",
    ("109", "000160", "PENN D 1"): "PR28",
    ("109", "000164", "PENN D 2"): "PR26",
}


def norm(value, width=None):
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return ""
    if width and text.isdigit():
        return text.zfill(width)
    return text.upper()


def party_bucket(party):
    """Normalize official party codes without duplicating cross-filed votes."""
    party = str(party or "").strip().upper()
    if party.startswith("DEM") or party == "D/R":
        return "dem"
    if party.startswith("REP"):
        return "rep"
    return "other"


def read_csv(path):
    return pd.read_csv(path, dtype=str)


def read_official_block_vtd_assignments():
    rows = []
    with zipfile.ZipFile(DATA / "BlockAssign_ST42_PA.zip") as archive:
        with archive.open("BlockAssign_ST42_PA_VTD.txt") as handle:
            next(handle, None)
            for raw in handle:
                parts = raw.decode("utf-8", errors="ignore").strip().split("|")
                if len(parts) >= 3:
                    rows.append((norm(parts[0], 15), norm(parts[1], 3), norm(parts[2], 6)))
    return pd.DataFrame(rows, columns=["block", "countyfp_dst", "dst_vtd"])


def read_source_vtd_code_crosswalk(path):
    if not path:
        return {}, {}
    frame = read_csv(path)
    result, name_targets = {}, defaultdict(set)
    for row in frame.itertuples(index=False):
        county, source_vtd, dst_vtd = norm(row.countyfp, 3), norm(row.source_vtd, 6), norm(row.dst_vtd, 6)
        result[(county, source_vtd)] = dst_vtd
        if hasattr(row, "source_name") and row.source_name:
            for key in historical_name_keys(row.source_name):
                name_targets[(county, key)].add(dst_vtd)
    return result, name_targets


def read_modern_exception_crosswalk(path):
    result = defaultdict(set)
    if not path:
        return result
    for row in read_csv(path).itertuples(index=False):
        result[(int(row.year), norm(row.countyfp, 3), norm(row.source_vtd, 6), str(row.precinct_name))].add(norm(row.live_vtd, 6))
    return result


def read_county_precinct_crosswalk(path):
    result = defaultdict(list)
    if not path:
        return result
    for row in read_csv(path).itertuples(index=False):
        targets = (norm(row.dst_vtd, 6), float(row.weight))
        key = compact_live_name(row.source_name)
        if key:
            result[(norm(row.countyfp, 3), key)].append(targets)
    return result


def read_vest_crosswalk(path):
    result = defaultdict(list)
    if not path:
        return result
    for row in read_csv(path).itertuples(index=False):
        target = (norm(row.dst_vtd, 6), float(row.weight))
        result[(norm(row.countyfp, 3), norm(row.source_vtd, 6))].append(target)
        result[(norm(row.countyfp, 3), compact_live_name(row.source_name))].append(target)
    return result


def read_area_weighted_district_memberships(scope, weight_mode="area", block_vtd_source=None):
    """Return (countyfp, vtd20) -> [(district, share)]."""
    cache_key = (scope, weight_mode, str(block_vtd_source or "default"))
    if cache_key in VTD_MEMBERSHIP_CACHE:
        return VTD_MEMBERSHIP_CACHE[cache_key]
    district_file, _ = SCOPES[scope]
    block_district = read_csv(CROSSWALKS / district_file)
    block_district["block"] = block_district["block"].map(lambda v: norm(v, 15))
    block_district["district"] = block_district["district"].map(lambda v: norm(v).lstrip("0") or "0")

    if block_vtd_source:
        block_vtd = read_csv(block_vtd_source)
    else:
        block_vtd = read_official_block_vtd_assignments() if weight_mode == "block_count" else read_csv(CROSSWALKS / "pa_block20_to_vtd20.csv")
    block_vtd["block"] = block_vtd["block"].map(lambda v: norm(v, 15))
    block_vtd["countyfp_dst"] = block_vtd["countyfp_dst"].map(lambda v: norm(v, 3))
    block_vtd["dst_vtd"] = block_vtd["dst_vtd"].map(lambda v: norm(v, 6))

    # Use actual 2020 block area, rather than block counts, when a VTD crosses
    # a legislative boundary.  The block crosswalk itself supplies the stable
    # identifiers; geometry supplies the area weight.
    blocks = gpd.read_file(
        f"zip://{(DATA / 'tl_2022_42_tabblock20.zip').resolve().as_posix()}",
        columns=["GEOID20", "geometry"],
    )
    blocks = blocks[["GEOID20", "geometry"]].rename(columns={"GEOID20": "block"})
    blocks["block"] = blocks["block"].map(lambda v: norm(v, 15))
    blocks["area"] = blocks.to_crs(CRS).geometry.area
    blocks = blocks[["block", "area"]]

    merged = block_vtd.merge(block_district, on="block", how="inner").merge(blocks, on="block", how="left")
    merged["area"] = pd.to_numeric(merged["area"], errors="coerce").fillna(1.0)
    measure = "area" if weight_mode == "area" else "block_count"
    if measure == "block_count":
        merged[measure] = 1.0
    else:
        merged[measure] = merged["area"]
    grouped = merged.groupby(["countyfp_dst", "dst_vtd", "district"], as_index=False)[measure].sum()
    totals = grouped.groupby(["countyfp_dst", "dst_vtd"], as_index=False)[measure].sum().rename(columns={measure: "total_measure"})
    grouped = grouped.merge(totals, on=["countyfp_dst", "dst_vtd"], how="left")
    grouped["share"] = grouped[measure] / grouped["total_measure"]

    result = defaultdict(list)
    for row in grouped.itertuples(index=False):
        result[(row.countyfp_dst, row.dst_vtd)].append((row.district, float(row.share)))
    VTD_MEMBERSHIP_CACHE[cache_key] = result
    return result


def read_vtd_chain(year):
    if year in VTD_CHAIN_CACHE:
        return VTD_CHAIN_CACHE[year]
    if year >= 2020:
        return None
    filename = "pa_vtd00_to_vtd20_block_chain.csv" if year < 2010 else "pa_vtd10_to_vtd20_block_chain.csv"
    path = CROSSWALKS / filename
    if not path.exists():
        VTD_CHAIN_CACHE[year] = None
        return None
    frame = read_csv(path)
    dst_county_column = "countyfp_dst" if "countyfp_dst" in frame.columns else "dst_countyfp"
    if dst_county_column != "dst_countyfp":
        frame = frame.rename(columns={dst_county_column: "dst_countyfp"})
    for column, width in [("countyfp", 3), ("src_vtd", 6), ("dst_countyfp", 3), ("dst_vtd", 6)]:
        frame[column] = frame[column].map(lambda v, w=width: norm(v, w))
    frame["weight"] = pd.to_numeric(frame["weight"], errors="coerce").fillna(0.0)
    frame = frame[(frame["weight"] > 0) & (frame["src_vtd"] != "")]
    VTD_CHAIN_CACHE[year] = frame
    return frame


def read_historical_precinct_crosswalk(year):
    """Read the maintained election-precinct to VTD20 allocation for a year."""
    if year in HISTORICAL_PRECINCT_CROSSWALK_CACHE:
        return HISTORICAL_PRECINCT_CROSSWALK_CACHE[year]
    path = CROSSWALKS / "pa_historical_precinct_to_vtd20.csv"
    result = defaultdict(list)
    if path.exists():
        frame = read_csv(path)
        frame = frame[pd.to_numeric(frame["year"], errors="coerce") == year]
        for row in frame.itertuples(index=False):
            county = norm(row.countyfp, 3)
            source = norm(row.source_precinct, 6)
            dst_county = norm(row.dst_countyfp, 3)
            dst_vtd = norm(row.dst_vtd, 6)
            try:
                weight = float(row.weight or 0)
            except (TypeError, ValueError):
                weight = 0.0
            if county and source and dst_county and dst_vtd and weight > 0:
                result[(county, source)].append((dst_county, dst_vtd, weight))
    HISTORICAL_PRECINCT_CROSSWALK_CACHE[year] = result
    return result


def read_modern_precinct_crosswalk(year):
    """Read maintained modern precinct-name to VTD20 allocations."""
    if year in MODERN_PRECINCT_CROSSWALK_CACHE:
        return MODERN_PRECINCT_CROSSWALK_CACHE[year]
    path = CROSSWALKS / "pa_modern_precinct_to_vtd20.csv"
    result = defaultdict(list)
    if path.exists():
        frame = read_csv(path)
        frame = frame[pd.to_numeric(frame["year"], errors="coerce") == year]
        for row in frame.itertuples(index=False):
            county = norm(row.countyfp, 3)
            source = normalize_modern_precinct_name(row.source_precinct)
            dst_county = norm(row.dst_countyfp, 3)
            dst_vtd = norm(row.dst_vtd, 6)
            try:
                weight = float(row.weight or 0)
            except (TypeError, ValueError):
                weight = 0.0
            if county and source and dst_county and dst_vtd and weight > 0:
                result[(county, source)].append((dst_county, dst_vtd, weight))
    MODERN_PRECINCT_CROSSWALK_CACHE[year] = result
    return result


def name_key(value):
    text = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    for token in ("VOTINGDISTRICT", "VOTINGDIST", "VTD"):
        text = text.replace(token, "")
    return text


def historical_name_keys(value):
    """Generate comparable keys for legacy ward/district abbreviations."""
    text = re.sub(r"\s+", " ", str(value or "").upper()).strip()
    text = text.replace("T0N", "TON")
    text = re.sub(r"\s*\((?:USC|CONG)\s+\d+\)\s*$", "", text)
    if not text:
        return set()
    variants = {text}
    base = re.split(r"\s+(?:W|D|T)\s+\d", text, maxsplit=1)[0].strip()
    if base and base != text:
        variants.add(base)
    tokens = text.split()
    x_positions = [i for i, token in enumerate(tokens) if token == "X"]
    if x_positions:
        x_variant = tokens[:]
        x_variant[x_positions[0]] = "VTD"
        if len(x_positions) > 1:
            x_variant[x_positions[1]] = "ED"
        variants.add(" ".join(x_variant))
    padded = []
    for item in list(variants):
        padded.append(re.sub(r"(?<![A-Z0-9])(\d)(?![A-Z0-9])", r"0\1", item))
    variants.update(padded)
    for source, replacements in {
        r"\bW\b": ["WARD", "WD"],
        r"\bD\b": ["DISTRICT", "DIST"],
        r"\bT\b": ["TOWNSHIP", "TWP"],
        r"\bP\b": ["PRECINCT", "PCT", "DISTRICT", "DIST"],
        r"\bX\b": ["PRECINCT", "PCT", "DISTRICT", "DIST"],
        r"\bWARD\b": ["WD"],
        r"\bDISTRICT\b": ["DIST"],
        r"\bTOWNSHIP\b": ["TWP"],
        r"\bTWP\b": [""],
        r"\bBOROUGH\b": ["BORO", ""],
    }.items():
        for replacement in replacements:
            variants.update(re.sub(source, replacement, item) for item in list(variants))
    # Add a conservative structural key that removes only precinct-type
    # words. This lets labels such as ``CONCORD D CENTRAL WEST`` match
    # ``CONCORD TWP PCT CENTRAL WEST`` without treating numbered precincts
    # as interchangeable.
    for item in list(variants):
        structural = re.sub(
            r"\b(?:VOTING|DISTRICT|DIST|PRECINCT|PCT|VTD|WARD|WD|TOWNSHIP|TWP|BOROUGH|BORO|ED)\b",
            " ",
            item,
        )
        structural = re.sub(r"\s+", " ", structural).strip()
        if structural:
            variants.add(structural)
    # Older election returns often omit the township marker, while Census
    # VTD labels include it (for example ``EAST GOSHEN P 09`` versus
    # ``EAST GOSHEN TWP PCT 09``). Keep this as an optional variant: the
    # numbered precinct still has to match an old VTD uniquely.
    for item in list(variants):
        if re.search(r"\b(?:TOWNSHIP|TWP|BOROUGH|BORO|CITY|TOWN)\b", item):
            continue
        marker = re.search(r"\b(?:VTD|PCT|PRECINCT|DIST|DISTRICT|ED)\b", item)
        if marker:
            variants.add(
                f"{item[:marker.start()].rstrip()} TWP {item[marker.start():].lstrip()}"
            )
    return {name_key(item) for item in variants if name_key(item)}


def expand_historical_alias_vtds(county, alias_keys, historical_aliases):
    """Resolve abbreviated legacy labels to split historical VTDs.

    Some exports report a parent ward/precinct label while Census VTD files
    contain child records such as ``WARD 01 PRECINCT 01`` and ``PRECINCT 02``.
    Exact aliases remain preferred; prefix expansion is used only when there
    is no exact match and is intentionally county-scoped.
    """
    matches = set()
    for alias_key in alias_keys:
        matches.update(historical_aliases.get((county, alias_key), set()))
    if matches:
        return matches
    for length in sorted({len(key) for key in alias_keys if len(key) >= 6}, reverse=True):
        specific_alias_keys = {key for key in alias_keys if len(key) == length}
        for (alias_county, historical_key), vtds in historical_aliases.items():
            if alias_county != county:
                continue
            if any(historical_key.startswith(alias_key) or alias_key.startswith(historical_key) for alias_key in specific_alias_keys):
                matches.update(vtds)
        if matches:
            return matches
    # Conservative fuzzy fallback for abbreviated legacy labels. Only accept
    # a unique single-VTD winner with a clear margin over the runner-up.
    source_text = name_key(normalize_modern_precinct_name(" ".join(alias_keys)))
    ranked = []
    for (alias_county, historical_key), vtds in historical_aliases.items():
        if alias_county != county or len(vtds) != 1:
            continue
        ranked.append((SequenceMatcher(None, source_text, historical_key).ratio(), vtds))
    ranked.sort(key=lambda item: item[0], reverse=True)
    if ranked and ranked[0][0] >= 0.84 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.05):
        return set(ranked[0][1])
    return matches


def normalize_modern_precinct_name(value):
    """Normalize county export abbreviations to the Census VTD spelling."""
    text = re.sub(r"\s+", " ", str(value or "").upper()).strip()
    text = re.sub(r"\s+-\s+(?:MAIL|FEDERAL|PROV|PROVISIONAL)\s*$", "", text)
    text = re.sub(r"\s*\((?:USC|CONG)\s+\d+\)\s*$", "", text)
    text = re.sub(r"\b(D|X|W)\s+(\d+)\s+\1\s+\2\b", r"\1 \2", text)
    text = re.sub(r"\bDIST\b", "DISTRICT", text)
    text = re.sub(r"\b(D|X)\s+(\d+)\b", r"DISTRICT \2", text)
    text = re.sub(r"\bTOWNSHIP\s+(\d+)\b", r"DISTRICT \1", text)
    text = re.sub(r"\bTOWNSHIP\s+(?=DISTRICT)", "", text)
    text = re.sub(r"\bW\s+(\d+)\b", r"WARD \1", text)
    text = re.sub(r"\bBR\b", "BOROUGH", text)
    text = re.sub(r"\bTP\b", "TOWNSHIP", text)
    text = re.sub(r"\bTWP\b", "TOWNSHIP", text)
    text = re.sub(r"\bTOWNSHIP\s+(?=DISTRICT)", "", text)
    text = re.sub(r"\bHT\b", "HEIGHTS", text)
    text = re.sub(r"\bHL\b", "HILLS", text)
    text = re.sub(r"\bMT\.", "MOUNT", text)
    text = re.sub(r"\bCASL\b", "CASTLE", text)
    tokens = text.split()
    if len(tokens) % 2 == 0 and tokens[: len(tokens) // 2] == tokens[len(tokens) // 2 :]:
        text = " ".join(tokens[: len(tokens) // 2])
    return text


def compact_live_name(value):
    text = normalize_modern_precinct_name(value)
    text = re.sub(r"\s*\(USC\s+\d+\)", "", text)
    text = re.sub(r"\b(?:TOWNSHIP|TWP|BOROUGH|BORO|WARD|WD|DISTRICT|DIST|PRECINCT|PCT|VTD|ED|X|P)\b", " ", text)
    text = re.sub(r"\b0+(\d+)\b", r"\1", text)
    return re.sub(r"[^A-Z0-9]", "", text)


def resolve_current_alias_vtds(county, precinct_name, aliases):
    """Resolve a modern name through exact or unique county-local prefixes."""
    exact = set()
    source_keys = historical_name_keys(precinct_name)
    source_keys.update(historical_name_keys(normalize_modern_precinct_name(precinct_name)))
    for key in source_keys:
        exact.update(aliases.get((county, key), set()))
    if exact:
        return exact
    if county not in CURRENT_ALIAS_PREFIX_CACHE:
        buckets = defaultdict(set)
        for (alias_county, alias_key), vtds in aliases.items():
            if alias_county == county:
                buckets[alias_key[:6]].add(alias_key)
        CURRENT_ALIAS_PREFIX_CACHE[county] = buckets
    candidates = set()
    for source_key in source_keys:
        for alias_key in CURRENT_ALIAS_PREFIX_CACHE[county].get(source_key[:6], set()):
            if source_key.startswith(alias_key) or alias_key.startswith(source_key):
                candidates.update(aliases.get((county, alias_key), set()))
    if len(candidates) == 1:
        return candidates

    global LIVE_SIMPLE_ALIAS_CACHE
    if LIVE_SIMPLE_ALIAS_CACHE is None and aliases is LIVE_ALIAS_CACHE:
        LIVE_SIMPLE_ALIAS_CACHE = defaultdict(set)
        for (alias_county, alias_key), vtds in aliases.items():
            LIVE_SIMPLE_ALIAS_CACHE[(alias_county, compact_live_name(alias_key))].update(vtds)
    if aliases is LIVE_ALIAS_CACHE and LIVE_SIMPLE_ALIAS_CACHE is not None:
        compact = compact_live_name(precinct_name)
        simple = LIVE_SIMPLE_ALIAS_CACHE.get((county, compact), set())
        if len(simple) == 1:
            return set(simple)

    # Some counties changed from compact local codes to descriptive names
    # after the Census.  Permit only a unique, high-confidence county-local
    # match; ambiguous names remain unresolved for manual review.
    best_score = 0.0
    second_score = 0.0
    best_vtds = set()
    source_text = name_key(normalize_modern_precinct_name(precinct_name))
    for (alias_county, alias_key), vtds in aliases.items():
        if alias_county != county:
            continue
        score = SequenceMatcher(None, source_text, alias_key).ratio()
        if score > best_score:
            second_score = best_score
            best_score = score
            best_vtds = set(vtds)
        elif score > second_score:
            second_score = score
    if best_score >= 0.82 and best_score - second_score >= 0.04 and len(best_vtds) == 1:
        return best_vtds
    return set()


def display_candidate_name(value):
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    words = []
    for word in text.split():
        if word.upper() in {"JR", "SR", "II", "III", "IV", "V"}:
            words.append(word.upper().replace("JR", "Jr").replace("SR", "Sr"))
        elif len(word) == 2 and word.endswith("."):
            words.append(word[0].upper() + ".")
        else:
            words.append(word[:1].upper() + word[1:].lower())
    result = " ".join(words)
    result = re.sub(r"\b([A-Z])\b(?!\.)", r"\1.", result)
    result = re.sub(r"\s+(Jr|Sr)\.?$", r", \1", result)
    result = re.sub(r"\bMccain\b", "McCain", result)
    result = re.sub(r"\bMccord\b", "McCord", result)
    if result in {"Thomas W. Corbett, Jr", "Thomas Corbett, Jr"}:
        result = "Tom Corbett"
    return result


def read_historical_vtd_aliases(year):
    if year in VTD_ALIAS_CACHE:
        return VTD_ALIAS_CACHE[year]
    if year >= 2020:
        return {}
    if year < 2010:
        vtd_path = DATA / "tiger2008_vtd00"
        vtd_columns = ["COUNTYFP00", "VTDST00", "NAME00", "NAMELSAD00"]
        county_col, vtd_col, name_cols = "COUNTYFP00", "VTDST00", ("NAME00", "NAMELSAD00")
        paths = sorted(vtd_path.glob("*_vtd00.zip"))
        if not paths:
            VTD_ALIAS_CACHE[year] = {}
            return VTD_ALIAS_CACHE[year]
        aliases = defaultdict(set)
        for path in paths:
            frame = gpd.read_file(
                f"zip://{path.resolve().as_posix()}",
                columns=vtd_columns,
            )
            for row in frame.itertuples(index=False):
                county = norm(getattr(row, county_col), 3)
                vtd = norm(getattr(row, vtd_col), 6)
                for label_col in name_cols:
                    for key in historical_name_keys(getattr(row, label_col)):
                        aliases[(county, key)].add(vtd)
        VTD_ALIAS_CACHE[year] = aliases
        return aliases
    frame = gpd.read_file(
        f"zip://{(DATA / 'tl_2012_42_vtd10.zip').resolve().as_posix()}",
        columns=["COUNTYFP10", "VTDST10", "NAME10", "NAMELSAD10"],
    )
    aliases = defaultdict(set)
    for row in frame.itertuples(index=False):
        county = norm(row.COUNTYFP10, 3)
        vtd = norm(row.VTDST10, 6)
        for label in (row.NAME10, row.NAMELSAD10):
            for key in historical_name_keys(label):
                aliases[(county, key)].add(vtd)
    VTD_ALIAS_CACHE[year] = aliases
    return aliases


def read_2011_proxy_aliases():
    """Read corrected 2011 county labels for reviewed historical proxies."""
    global PROXY_ALIAS_CACHE
    if PROXY_ALIAS_CACHE is not None:
        return PROXY_ALIAS_CACHE
    path = DATA / "pa_election_geodata_2011_boundaries" / "2011 Voting District Boundary Shapefiles" / "VTDS.shp"
    frame = gpd.read_file(path, columns=["COUNTYFP10", "GEOID10", "NAME10", "NAMELSAD10"])
    aliases = defaultdict(set)
    for row in frame.itertuples(index=False):
        county = norm(row.COUNTYFP10, 3)
        geoid = str(row.GEOID10 or "").split(".", 1)[0]
        vtd = norm(geoid[5:] if geoid.isdigit() else "", 6)
        if not county or not vtd:
            continue
        for label in (row.NAME10, row.NAMELSAD10):
            for key in historical_name_keys(label):
                aliases[(county, key)].add(vtd)
    PROXY_ALIAS_CACHE = aliases
    return aliases


def read_current_vtd_aliases():
    frame = gpd.read_file(
        f"zip://{(DATA / 'tl_2020_42_vtd20.zip').resolve().as_posix()}",
        columns=["COUNTYFP20", "VTDST20", "NAME20", "NAMELSAD20"],
    )
    county_col, vtd_col, name_cols = "COUNTYFP20", "VTDST20", ("NAME20", "NAMELSAD20")
    aliases = defaultdict(set)
    for row in frame.itertuples(index=False):
        county = norm(getattr(row, county_col), 3)
        vtd = norm(getattr(row, vtd_col), 6)
        for name_col in name_cols:
            label = getattr(row, name_col)
            key = name_key(label)
            if key:
                aliases[(county, key)].add(vtd)
    return aliases


def read_live_vtd_crosswalk():
    global LIVE_VTD_CROSSWALK_CACHE
    if LIVE_VTD_CROSSWALK_CACHE is not None:
        return LIVE_VTD_CROSSWALK_CACHE
    path = CROSSWALKS / "pa_live_vtd_to_vtd20.csv"
    if not path.exists():
        LIVE_VTD_CROSSWALK_CACHE = {}
        return LIVE_VTD_CROSSWALK_CACHE
    frame = read_csv(path)
    result = defaultdict(list)
    for row in frame.itertuples(index=False):
        result[(norm(row.src_countyfp, 3), norm(row.src_vtd, 6))].append(
            (norm(row.dst_countyfp, 3), norm(row.dst_vtd, 6), float(row.weight))
        )
    LIVE_VTD_CROSSWALK_CACHE = result
    return result


def read_live_vtd_aliases():
    global LIVE_ALIAS_CACHE
    if LIVE_ALIAS_CACHE is not None:
        return LIVE_ALIAS_CACHE
    path = DATA / "pa_live_voting_districts_current.geojson"
    aliases = defaultdict(set)
    if path.exists():
        frame = gpd.read_file(path, columns=["COUNTY", "VTD", "NAME"])
        for row in frame.itertuples(index=False):
            county = norm(row.COUNTY, 3)
            vtd = norm(row.VTD, 6)
            for key in historical_name_keys(row.NAME):
                aliases[(county, key)].add(vtd)
            for key in historical_name_keys(normalize_modern_precinct_name(row.NAME)):
                aliases[(county, key)].add(vtd)
    LIVE_ALIAS_CACHE = aliases
    return aliases


def read_live_vtd_districts(scope):
    if scope in LIVE_DISTRICT_CACHE:
        return LIVE_DISTRICT_CACHE[scope]
    path = CROSSWALKS / f"pa_live_unmapped_vtd_to_{scope}_tabblocks.csv"
    result = defaultdict(list)
    if path.exists():
        frame = read_csv(path)
        for row in frame.itertuples(index=False):
            result[(norm(row.src_countyfp, 3), norm(row.src_vtd, 6))].append(
                (norm(row.district).lstrip("0") or "0", float(row.weight))
            )
    LIVE_DISTRICT_CACHE[scope] = result
    return result


def live_vtd_district_targets(scope, county, vtd, memberships):
    """Resolve a live VTD through the live-to-Census chain or tabblock fallback."""
    cache_key = (scope, county, vtd)
    if cache_key in LIVE_TARGET_CACHE:
        return LIVE_TARGET_CACHE[cache_key]
    crosswalk_targets = read_live_vtd_crosswalk().get((county, vtd), [])
    if crosswalk_targets:
        result = []
        for dst_county, dst_vtd, chain_weight in crosswalk_targets:
            for district, district_weight in memberships[scope].get((dst_county, dst_vtd), []):
                result.append((district, chain_weight * district_weight))
        if result:
            LIVE_TARGET_CACHE[cache_key] = result
            return result
    result = read_live_vtd_districts(scope).get((county, vtd), [])
    LIVE_TARGET_CACHE[cache_key] = result
    return result


def read_historical_geometry_targets(year, source_keys, source_path=None):
    """Map historical election precinct IDs to weighted VTD20 targets.

    The PA 2011 boundary package carries the election-era precinct identifier
    in GEOID10.  We use its polygons as the source geography and intersect
    them with the current VTD20 polygons, producing the same target format as
    the block-chain crosswalk.  This is intentionally a fallback: existing
    Census VTD chains and name matches remain authoritative when available.
    """
    if year not in {2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014, 2018, 2020, 2022, 2024}:
        return {}
    source_path = source_path or DATA / "pa_election_geodata_2011_boundaries" / "2011 Voting District Boundary Shapefiles" / "VTDS.shp"
    cache_key = (year, str(Path(source_path).resolve()))
    if cache_key in HISTORICAL_GEOMETRY_CACHE:
        cached = HISTORICAL_GEOMETRY_CACHE[cache_key]
        return {key: cached.get(key, cached.get((key[0], key[1]), [])) for key in source_keys}

    def read_source(path, ignore_geometry=False):
        if Path(path).is_dir():
            frames = []
            for archive in sorted(Path(path).glob("*.zip")):
                frames.append(gpd.read_file(f"zip://{archive.resolve().as_posix()}", ignore_geometry=ignore_geometry))
            return pd.concat(frames, ignore_index=True) if frames else gpd.GeoDataFrame()
        return gpd.read_file(path, ignore_geometry=ignore_geometry)

    historical = read_source(source_path, ignore_geometry=True)
    columns = set(historical.columns)
    if {"COUNTYFP10", "GEOID10"}.issubset(columns):
        historical["countyfp"] = historical["COUNTYFP10"].map(lambda v: norm(v, 3))
        historical["src_vtd"] = historical["GEOID10"].map(
            lambda v: norm(str(v).split(".", 1)[0][5:], 6) if str(v).split(".", 1)[0].isdigit() else ""
        )
        name_columns = [column for column in ("NAME10", "NAMELSAD10") if column in columns]
    elif {"COUNTYFP00", "VTDST00"}.issubset(columns):
        historical["countyfp"] = historical["COUNTYFP00"].map(lambda v: norm(v, 3))
        historical["src_vtd"] = historical["VTDST00"].map(lambda v: norm(v, 6))
        name_columns = [column for column in ("NAME00", "NAMELSAD00") if column in columns]
    elif {"COUNTYFP20", "VTDST20"}.issubset(columns):
        # Pennsylvania's official 2021 geography release is based on the
        # 2020 VTD identifiers, so it can also be used directly as a modern
        # name-to-VTD reference.
        historical["countyfp"] = historical["COUNTYFP20"].map(lambda v: norm(v, 3))
        historical["src_vtd"] = historical["VTDST20"].map(lambda v: norm(v, 6))
        name_columns = [column for column in ("NAME20", "NAMELSAD20", "NAME") if column in columns]
    elif {"FIPS", "VTD"}.issubset(columns):
        historical["countyfp"] = historical["FIPS"].map(lambda v: norm(v, 3))
        historical["src_vtd"] = historical["VTD"].map(lambda v: norm(v, 6))
        name_columns = [column for column in ("NAME",) if column in columns]
    else:
        raise ValueError(f"Unsupported historical geometry fields in {source_path}")
    direct_vtd_source = {"COUNTYFP20", "VTDST20"}.issubset(columns) or {"FIPS", "VTD"}.issubset(columns)
    historical["name_keys"] = historical.apply(
        lambda row: set().union(*(historical_name_keys(row[column]) for column in name_columns)) | set().union(*(compact_live_name(row[column]) for column in name_columns)),
        axis=1,
    )
    requested = {(key[0], key[1]) for key in source_keys}
    has_name_only_sources = any(key[1] == "000000" for key in source_keys)
    if has_name_only_sources:
        counties = {key[0] for key in source_keys}
        historical = historical[historical["countyfp"].isin(counties)].copy()
    else:
        historical = historical[
            historical.apply(lambda row: (row["countyfp"], row["src_vtd"]) in requested, axis=1)
        ].copy()
    if historical.empty:
        HISTORICAL_GEOMETRY_CACHE[cache_key] = {}
        return {key: [] for key in source_keys}

    if direct_vtd_source:
        historical["source_area"] = 1.0
    else:
        historical = read_source(source_path)
        if {"COUNTYFP00", "VTDST00"}.issubset(historical.columns):
            historical["countyfp"] = historical["COUNTYFP00"].map(lambda v: norm(v, 3))
            historical["src_vtd"] = historical["VTDST00"].map(lambda v: norm(v, 6))
        else:
            historical["countyfp"] = historical["COUNTYFP10"].map(lambda v: norm(v, 3))
            historical["src_vtd"] = historical["GEOID10"].map(
                lambda v: norm(str(v).split(".", 1)[0][5:], 6) if str(v).split(".", 1)[0].isdigit() else ""
            )
        historical["name_keys"] = historical.apply(
            lambda row: set().union(*(historical_name_keys(row[column]) for column in name_columns)) | set().union(*(compact_live_name(row[column]) for column in name_columns)),
            axis=1,
        )
    result = defaultdict(list)

    if direct_vtd_source:
        for row in historical.itertuples(index=False):
            result[(row.countyfp, row.src_vtd)].append((row.countyfp, row.src_vtd, 1.0))
    else:
        targets = gpd.read_file(
            f"zip://{(DATA / 'tl_2020_42_vtd20.zip').resolve().as_posix()}",
            columns=["COUNTYFP20", "VTDST20", "geometry"],
        )
        historical = historical.to_crs(CRS)
        historical["source_area"] = historical.geometry.area
        targets = targets.to_crs(CRS)

    for county in [] if direct_vtd_source else sorted(historical["countyfp"].unique()):
        left = historical[historical["countyfp"] == county].copy()
        right = targets[targets["COUNTYFP20"].map(lambda v: norm(v, 3)) == county].copy()
        if left.empty or right.empty:
            continue
        right["dst_countyfp"] = right["COUNTYFP20"].map(lambda v: norm(v, 3))
        right["dst_vtd"] = right["VTDST20"].map(lambda v: norm(v, 6))
        joined = gpd.sjoin(left, right[["dst_countyfp", "dst_vtd", "geometry"]], how="inner", predicate="intersects")
        if joined.empty:
            continue
        right_geometries = right.geometry
        intersections = []
        for row in joined.itertuples():
            target_geometry = right_geometries.loc[row.index_right]
            intersections.append(row.geometry.intersection(target_geometry).area)
        joined["intersection_area"] = intersections
        joined = joined[joined["intersection_area"] > 0]
        totals = joined.groupby(["countyfp", "src_vtd"], as_index=False)["intersection_area"].sum().rename(columns={"intersection_area": "total_area"})
        joined = joined.merge(totals, on=["countyfp", "src_vtd"], how="left")
        joined["weight"] = joined["intersection_area"] / joined["total_area"]
        for row in joined.itertuples(index=False):
            result[(row.countyfp, row.src_vtd)].append((row.dst_countyfp, row.dst_vtd, float(row.weight)))

    if has_name_only_sources:
        # Modern OpenElections exports often omit the numeric VTD code. Match
        # the municipality/ward prefix to the historical boundary names, then
        # aggregate each polygon's VTD20 weights by its area.
        name_index = defaultdict(list)
        for row in historical.itertuples(index=False):
            for key in row.name_keys:
                name_index[(row.countyfp, key)].append(row)
        for source_key in source_keys:
            county, source_vtd, source_name = source_key
            if source_vtd != "000000":
                continue
            source_keys_normalized = historical_name_keys(source_name)
            source_keys_normalized.add(compact_live_name(source_name))
            if not source_keys_normalized:
                continue
            candidate_rows = []
            for source_key_value in source_keys_normalized:
                candidate_rows.extend(name_index.get((county, source_key_value), []))
            weighted = defaultdict(float)
            seen_rows = set()
            for row in candidate_rows:
                row_id = id(row)
                if row_id in seen_rows:
                    continue
                seen_rows.add(row_id)
                matching = any(
                    source_key_value.startswith(candidate_key) or candidate_key.startswith(source_key_value)
                    for source_key_value in source_keys_normalized
                    for candidate_key in row.name_keys
                )
                if not matching:
                    continue
                for dst_county, dst_vtd, share in result.get((county, row.src_vtd), []):
                    weighted[(dst_county, dst_vtd)] += float(row.source_area) * share
            total = sum(weighted.values())
            if total > 0:
                result[source_key] = [
                    (dst_county, dst_vtd, value / total)
                    for (dst_county, dst_vtd), value in sorted(weighted.items())
                ]

    HISTORICAL_GEOMETRY_CACHE[cache_key] = dict(result)
    cached = HISTORICAL_GEOMETRY_CACHE[cache_key]
    return {key: cached.get(key, cached.get((key[0], key[1]), [])) for key in source_keys}


def parse_precinct_returns(path, year, office_code):
    """Aggregate one raw PA export into county/source-VTD vote rows."""
    office_names = {
        "USP": "PRESIDENT",
        "USS": "U.S. SENATE",
        "GOV": "GOVERNOR",
        "ATT": "ATTORNEY GENERAL",
        "AUD": "AUDITOR GENERAL",
        "TRE": "STATE TREASURER",
        "USC": "U.S. HOUSE",
    }
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        first = next(reader, None)
        if first and {str(value).strip().lower() for value in first} >= {"county", "precinct", "office", "party", "votes"}:
            county_frame = gpd.read_file(DATA / "pa_counties.geojson", columns=["COUNTYFP20", "NAME20"])
            county_lookup = {
                str(row.COUNTYFP20).zfill(3): norm(row.NAME20).replace(" COUNTY", "")
                for row in county_frame.itertuples(index=False)
            }
            county_names = {name: fips for fips, name in county_lookup.items()}
            columns = {str(value).strip().lower(): index for index, value in enumerate(first)}
            precinct_idx = columns["precinct"]
            county_idx = columns["county"]
            office_idx = columns["office"]
            party_idx = columns["party"]
            votes_idx = columns["votes"]
            candidate_idx = columns["candidate"]
            totals = defaultdict(lambda: {"dem": 0.0, "rep": 0.0, "other": 0.0})
            candidates = {"dem": "", "rep": ""}
            wanted_office = office_names.get(office_code.upper(), office_code.upper())
            for row in reader:
                if len(row) <= max(county_idx, precinct_idx, office_idx, party_idx, votes_idx, candidate_idx):
                    continue
                if norm(row[office_idx]) != wanted_office:
                    continue
                county_name = norm(row[county_idx]).replace(" COUNTY", "")
                county = county_names.get(county_name)
                raw_precinct_name = re.sub(r"\s+", " ", row[precinct_idx].upper()).strip()
                if county == "101" and re.fullmatch(r"\d{2}~\d{2}", raw_precinct_name):
                    precinct_name = f"PHILADELPHIA WARD {raw_precinct_name[:2]} PRECINCT {raw_precinct_name[3:]}"
                else:
                    precinct_name = normalize_modern_precinct_name(raw_precinct_name)
                if not county or not precinct_name:
                    continue
                try:
                    votes = float(row[votes_idx] or 0)
                except ValueError:
                    continue
                party = row[party_idx].strip().upper()
                bucket = party_bucket(party)
                totals[(county, "000000", precinct_name)][bucket] += votes
                if bucket in {"dem", "rep"} and not candidates[bucket]:
                    candidates[bucket] = display_candidate_name(row[candidate_idx])
            return totals, candidates

    # The 2016 and 2020 exports differ by two trailing geography columns.
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.reader(handle)
        first_row = next(reader, None)
        if (
            year >= 2016
            and first_row
            and len(first_row) > 30
            and re.fullmatch(r"\d+", first_row[29].strip())
            and re.fullmatch(r"\d+", first_row[30].strip())
        ):
            totals = defaultdict(lambda: {"dem": 0.0, "rep": 0.0, "other": 0.0})
            candidates = {"dem": "", "rep": ""}
            for row in [first_row] + list(reader):
                if len(row) <= 30 or row[8].strip().upper() != office_code.upper():
                    continue
                county = norm(row[29], 3)
                vtd = norm(row[30], 6)
                if not county or not vtd:
                    continue
                try:
                    votes = float(row[15] or 0)
                except ValueError:
                    continue
                party = row[9].strip().upper()
                bucket = party_bucket(party)
                precinct_name = normalize_modern_precinct_name(row[22])
                totals[(county, vtd, precinct_name)][bucket] += votes
                if bucket in {"dem", "rep"} and not candidates[bucket]:
                    candidates[bucket] = display_candidate_name(" ".join(row[11:15]))
            return totals, candidates

    county_idx, precinct_idx, name_idx = (29, 30, 22) if year >= 2020 else (27, 28, 20)
    totals = defaultdict(lambda: {"dem": 0.0, "rep": 0.0, "other": 0.0})
    candidates = {"dem": "", "rep": ""}
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if len(row) <= precinct_idx or row[8].strip().upper() != office_code.upper():
                continue
            county = norm(row[county_idx], 3)
            # Older PA exports sometimes leave the numeric VTD code blank even
            # though the precinct name is populated. Preserve those rows for
            # the historical name/geometry resolver instead of dropping them.
            precinct = norm(row[precinct_idx], 6) or "000000"
            if not county:
                continue
            try:
                votes = float(row[15] or 0)
            except ValueError:
                continue
            party = row[9].strip().upper()
            bucket = party_bucket(party)
            precinct_label = " ".join(part for part in row[name_idx:name_idx + 5] if part).strip()
            precinct_name = re.sub(r"\s+", " ", precinct_label.upper()).strip()
            totals[(county, precinct, precinct_name)][bucket] += votes
            if bucket in {"dem", "rep"} and not candidates[bucket]:
                name = " ".join(x for x in [row[12], row[13], row[11], row[14]] if x).strip()
                candidates[bucket] = display_candidate_name(name)
    return totals, candidates


def parse_historical_vtd_returns(path, year):
    """Read a historical VTD layer whose 2016 votes are already on VTD10."""
    if year != 2016:
        raise ValueError("The historical VTD source currently supports only 2016")
    frame = gpd.read_file(
        f"zip://{Path(path).resolve().as_posix()}" if str(path).lower().endswith(".zip")
        else str(Path(path).resolve()),
        columns=["COUNTYFP10", "VTDST10", "T16PRESD", "T16PRESR", "T16PRESOTH"],
    )
    totals = {}
    candidates = {"dem": "Hillary Clinton", "rep": "Donald J Trump"}
    for row in frame.itertuples(index=False):
        county = norm(row.COUNTYFP10, 3)
        vtd = norm(row.VTDST10, 6)
        if not county or not vtd:
            continue
        totals[(county, vtd, "")] = {
            "dem": float(row.T16PRESD or 0),
            "rep": float(row.T16PRESR or 0),
            "other": float(row.T16PRESOTH or 0),
        }
    return totals, candidates


def district_result_rows(votes, candidates):
    # Pennsylvania's official export stores 2020 names surname-first. Keep the
    # public district files aligned with the county-result labels.
    if candidates.get("dem") == "Biden Joseph Robinette, Jr":
        candidates = {**candidates, "dem": "Joe Biden"}
    if candidates.get("rep") == "Trump Donald J.":
        candidates = {**candidates, "rep": "Donald J. Trump"}
    results = {}
    for district, values in sorted(votes.items(), key=lambda item: int(item[0]) if item[0].isdigit() else item[0]):
        dem = int(round(values["dem"]))
        rep = int(round(values["rep"]))
        other = int(round(values["other"]))
        total = dem + rep + other
        margin = dem - rep
        results[district] = {
            "dem_votes": dem,
            "rep_votes": rep,
            "other_votes": other,
            "total_votes": total,
            "dem_candidate": candidates["dem"],
            "rep_candidate": candidates["rep"],
            "winner": "D" if margin > 0 else "R" if margin < 0 else "T",
            "margin": float(abs(margin)),
            "margin_pct": (abs(margin) / total * 100) if total else 0.0,
        }
    return results


def apply_dra_presidential_shares(scope, contest, year, results):
    """Apply checked DRA presidential shares while retaining rebuilt turnout."""
    if contest != "president" or scope not in {"state_house", "state_senate"}:
        return ""
    label = "state house" if scope == "state_house" else "state senate"
    path = DATA / f"district-statistics {label} {year} Pres.csv"
    if not path.exists():
        return ""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            district = norm(row.get("ID")).lstrip("0") or "0"
            result = results.get(district)
            if not result:
                continue
            shares = []
            for key in ("Dem", "Rep", "Oth"):
                try:
                    shares.append(max(float(row.get(key) or 0), 0.0))
                except ValueError:
                    shares.append(0.0)
            share_total = sum(shares)
            if share_total <= 0:
                continue
            shares = [share / share_total for share in shares]
            total = int(result["total_votes"])
            raw = [total * share for share in shares]
            allocated = [int(value) for value in raw]
            for index in sorted(range(3), key=lambda i: raw[i] - allocated[i], reverse=True)[: total - sum(allocated)]:
                allocated[index] += 1
            result["dem_votes"], result["rep_votes"], result["other_votes"] = allocated
            margin = allocated[0] - allocated[1]
            result["winner"] = "D" if margin > 0 else "R" if margin < 0 else "T"
            result["margin"] = float(abs(margin))
            result["margin_pct"] = abs(margin) / total * 100 if total else 0.0
    return path.name


def apply_exact_district_benchmarks(scope, contest, year, results):
    """Replace reviewed district rows with sourced exact-vote benchmarks."""
    path = DATA / "benchmarks" / f"pa_{scope}_{year}_{contest}.csv"
    if not path.exists():
        return ""
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            district = norm(row.get("district")).lstrip("0") or "0"
            result = results.get(district)
            if not result:
                continue
            dem = int(float(row.get("dem_votes") or 0))
            rep = int(float(row.get("rep_votes") or 0))
            other = int(float(row.get("other_votes") or 0))
            total = dem + rep + other
            margin = dem - rep
            result.update({
                "dem_votes": dem,
                "rep_votes": rep,
                "other_votes": other,
                "total_votes": total,
                "winner": "D" if margin > 0 else "R" if margin < 0 else "T",
                "margin": float(abs(margin)),
                "margin_pct": abs(margin) / total * 100 if total else 0.0,
            })
    return path.relative_to(DATA).as_posix()


def read_statewide_vote_control(contest, year):
    """Return authoritative statewide party totals for district-layer raking."""
    benchmark = DATA / "benchmarks" / f"pa_congressional_{year}_{contest}.csv"
    if benchmark.exists():
        totals = {"dem_votes": 0, "rep_votes": 0, "other_votes": 0}
        with benchmark.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
        if rows:
            for row in rows:
                for field in totals:
                    totals[field] += int(float(row.get(field) or 0))
            return totals, benchmark.relative_to(DATA).as_posix()

    path = DATA / "contests" / f"{contest}_{year}.json"
    if not path.exists():
        return {}, ""
    document = json.loads(path.read_text(encoding="utf-8"))
    totals = {
        field: sum(int(row.get(field) or 0) for row in document.get("rows", []))
        for field in ("dem_votes", "rep_votes", "other_votes")
    }
    return totals, path.relative_to(DATA).as_posix()


def apply_statewide_vote_control(contest, year, results):
    """Rake district party totals to statewide controls with exact rounding."""
    controls, source = read_statewide_vote_control(contest, year)
    if not controls or not results:
        return ""
    districts = sorted(results, key=lambda value: int(value) if value.isdigit() else value)
    for field, target in controls.items():
        observed = sum(int(results[district].get(field) or 0) for district in districts)
        if observed > 0:
            basis = [int(results[district].get(field) or 0) for district in districts]
        else:
            # Some rounded DRA tables omit minor-party votes entirely. In that
            # case district turnout is the least-distorting allocation basis.
            basis = [int(results[district].get("total_votes") or 0) for district in districts]
            observed = sum(basis)
        if observed <= 0:
            continue
        raw = [value * target / observed for value in basis]
        allocated = [int(value) for value in raw]
        remainder = target - sum(allocated)
        order = sorted(range(len(raw)), key=lambda index: raw[index] - allocated[index], reverse=True)
        for index in order[:remainder]:
            allocated[index] += 1
        for district, value in zip(districts, allocated):
            results[district][field] = value

    for result in results.values():
        dem = int(result["dem_votes"])
        rep = int(result["rep_votes"])
        other = int(result["other_votes"])
        total = dem + rep + other
        margin = dem - rep
        result.update({
            "total_votes": total,
            "winner": "D" if margin > 0 else "R" if margin < 0 else "T",
            "margin": float(abs(margin)),
            "margin_pct": abs(margin) / total * 100 if total else 0.0,
        })
    return source


def expected_districts(scope):
    _, filename = SCOPES[scope]
    frame = pd.read_csv(DATA / filename, dtype=str)
    return {norm(v).lstrip("0") or "0" for v in frame["district"]}


def normalize_vtd_targets(targets):
    """Collapse duplicate VTD paths and return one unit-sum allocation."""
    collapsed = defaultdict(float)
    for county, vtd, weight in targets:
        weight = float(weight or 0)
        if county and vtd and weight > 0:
            collapsed[(county, vtd)] += weight
    total = sum(collapsed.values())
    if total <= 0:
        return []
    return [
        (county, vtd, weight / total)
        for (county, vtd), weight in sorted(collapsed.items())
    ]


def build_one(year, source_file, contest, office_code, out_dir, weight_mode, scopes=None, historical_vtd_source=None, historical_geometry_source=None, block_vtd_source=None, source_vtd_source=None, exception_source=None, county_precinct_source=None, vest_crosswalk_source=None):
    if historical_vtd_source:
        source_votes, candidates = parse_historical_vtd_returns(historical_vtd_source, year)
    else:
        source_votes, candidates = parse_precinct_returns(source_file, year, office_code)
    source_total = sum(
        float(value or 0)
        for row in source_votes.values()
        for value in row.values()
    )
    selected_scopes = scopes or list(SCOPES)
    district_votes = {scope: defaultdict(lambda: {"dem": 0.0, "rep": 0.0, "other": 0.0}) for scope in selected_scopes}
    memberships = {scope: read_area_weighted_district_memberships(scope, weight_mode, block_vtd_source) for scope in selected_scopes}
    chain = read_vtd_chain(year)
    maintained_historical_targets = read_historical_precinct_crosswalk(year) if year < 2018 else {}
    maintained_modern_targets = read_modern_precinct_crosswalk(year) if year >= 2018 else {}
    historical_aliases = read_historical_vtd_aliases(year)
    fallback_year = 2010 if year == 2008 else 2008 if year == 2010 else None
    fallback_chain = read_vtd_chain(fallback_year) if fallback_year else None
    fallback_maintained_targets = read_historical_precinct_crosswalk(fallback_year) if fallback_year else {}
    fallback_aliases = read_historical_vtd_aliases(fallback_year) if fallback_year else None
    # The local 2011 boundary file is useful for auditing names, but its
    # GEOID10 values are not the source IDs used by the 2010 block-chain
    # layer. Keep the Census VTD10 alias layer for production proxies.
    proxy_aliases = read_historical_vtd_aliases(2010) if year < 2008 else None
    proxy_chain = read_vtd_chain(2010) if year < 2008 else None
    current_aliases = read_current_vtd_aliases() if year >= 2020 else {}
    live_aliases = read_live_vtd_aliases() if (year >= 2020 or exception_source) else {}
    source_code_crosswalk, source_name_crosswalk = read_source_vtd_code_crosswalk(source_vtd_source)
    modern_exceptions = read_modern_exception_crosswalk(exception_source)
    county_precincts = read_county_precinct_crosswalk(county_precinct_source)
    vest_crosswalk = read_vest_crosswalk(vest_crosswalk_source)

    if chain is None:
        source_to_target = defaultdict(list)
        for county, vtd, _name in source_votes:
            mapped_vtd = source_code_crosswalk.get((county, vtd), vtd)
            if mapped_vtd == vtd:
                name_targets = set()
                for key in historical_name_keys(_name):
                    name_targets.update(source_name_crosswalk.get((county, key), set()))
                if len(name_targets) == 1:
                    mapped_vtd = next(iter(name_targets))
            source_to_target[(county, vtd, _name)].append((county, mapped_vtd, 1.0))
    else:
        source_to_target = defaultdict(list)
        for row in chain.itertuples(index=False):
            source_to_target[(row.countyfp, row.src_vtd)].append((row.dst_countyfp, row.dst_vtd, float(row.weight)))
    geometry_source_keys = list(source_votes.keys())
    if year == 2006:
        geometry_source_keys.extend(
            (county, alias_vtd, "")
            for (county, _source_vtd), alias_vtd in PA_2006_GEOMETRY_CODE_ALIASES.items()
        )
    geometry_targets = read_historical_geometry_targets(
        year,
        geometry_source_keys,
        historical_geometry_source,
    ) if historical_geometry_source else {}
    fallback_source_to_target = defaultdict(list)
    if fallback_chain is not None:
        for row in fallback_chain.itertuples(index=False):
            fallback_source_to_target[(row.countyfp, row.src_vtd)].append((row.dst_countyfp, row.dst_vtd, float(row.weight)))

    unmatched = 0
    unmatched_votes = 0.0
    unmatched_keys = []
    membership_gap_votes = defaultdict(float)
    membership_gap_keys = defaultdict(list)
    for source_key, values in source_votes.items():
        county, source_vtd, precinct_name = source_key
        vest_targets = vest_crosswalk.get((county, compact_live_name(precinct_name)), [])
        if vest_targets:
            vest_assigned = False
            for scope in selected_scopes:
                for vtd, vest_weight in vest_targets:
                    for district, district_weight in memberships[scope].get((county, vtd), []):
                        vest_assigned = True
                        for bucket in values:
                            district_votes[scope][district][bucket] += values[bucket] * vest_weight * district_weight
            if vest_assigned:
                continue
        county_targets = []
        county_targets.extend(county_precincts.get((county, compact_live_name(precinct_name)), []))
        if county_targets:
            county_assigned = False
            for scope in selected_scopes:
                for vtd, county_weight in county_targets:
                    for district, district_weight in memberships[scope].get((county, vtd), []):
                        county_assigned = True
                        for bucket in values:
                            district_votes[scope][district][bucket] += values[bucket] * county_weight * district_weight
            if county_assigned:
                continue
        targets = []
        if year < 2018:
            historical_key = precinct_name if source_vtd == "000000" else source_vtd
            targets = maintained_historical_targets.get((county, norm(historical_key, 6)), [])
        else:
            targets = maintained_modern_targets.get(
                (county, normalize_modern_precinct_name(precinct_name)), []
            )
        if not targets and source_vtd != "000000":
            targets = source_to_target.get((county, source_vtd, precinct_name), []) if chain is None else source_to_target.get((county, source_vtd), [])
        if not targets and modern_exceptions:
            exception_vtds = set(modern_exceptions.get((year, county, source_vtd, precinct_name), set()))
            exception_vtds.update(resolve_current_alias_vtds(county, precinct_name, live_aliases))
            direct = {
                scope: [
                    target
                    for vtd in exception_vtds
                    for target in live_vtd_district_targets(scope, county, vtd, memberships)
                ]
                for scope in selected_scopes
            }
            if any(direct.values()):
                for scope, district_targets in direct.items():
                    for district, district_weight in district_targets:
                        for bucket in values:
                            district_votes[scope][district][bucket] += values[bucket] * district_weight
                continue
        if year >= 2020 and source_vtd == "000000":
            alias_vtds = resolve_current_alias_vtds(county, precinct_name, current_aliases)
            if alias_vtds:
                targets = [(county, vtd, 1.0) for vtd in sorted(alias_vtds)]
        if year >= 2020 and not targets:
            live_vtds = resolve_current_alias_vtds(county, precinct_name, live_aliases)
            live_vtds.update(modern_exceptions.get((year, county, source_vtd, precinct_name), set()))
            direct = {
                scope: [(district, weight) for vtd in live_vtds for district, weight in live_vtd_district_targets(scope, county, vtd, memberships)]
                for scope in selected_scopes
            }
            if any(direct.values()):
                for scope, district_targets in direct.items():
                    for district, district_weight in district_targets:
                        for bucket in values:
                            district_votes[scope][district][bucket] += values[bucket] * district_weight
                continue
        target_has_membership = any(
            memberships[scope].get((target_county, target_vtd))
            for target_county, target_vtd, _weight in targets
            for scope in selected_scopes
        )
        if year < 2020 and targets and not target_has_membership:
            # A legacy export code is not useful merely because it produced a
            # syntactically valid target. Retry by precinct name when that VTD
            # has no membership on the modern geometry.
            targets = []
        if year >= 2020 and source_vtd != "000000" and (not source_vtd_source or not target_has_membership):
            live_vtds = {source_vtd}
            live_vtds.update(resolve_current_alias_vtds(county, precinct_name, live_aliases))
            live_vtds.update(modern_exceptions.get((year, county, source_vtd, precinct_name), set()))
            direct = {
                scope: [
                    target
                    for vtd in live_vtds
                    for target in live_vtd_district_targets(scope, county, vtd, memberships)
                ]
                for scope in selected_scopes
            }
            if any(direct.values()):
                for scope, district_targets in direct.items():
                    for district, district_weight in district_targets:
                        for bucket in values:
                            district_votes[scope][district][bucket] += values[bucket] * district_weight
                continue
        if not targets and year < 2020:
            if year == 2008 and fallback_source_to_target:
                proxy_vtd = PA_2008_VTD10_PROXY_ALIASES.get(source_key)
                if proxy_vtd:
                    proxy_keys = {norm(proxy_vtd, 6), str(proxy_vtd).upper().zfill(6)}
                    for proxy_key in proxy_keys:
                        targets.extend(fallback_maintained_targets.get((county, proxy_key), []))
                        targets.extend(fallback_source_to_target.get((county, proxy_key), []))
            alias_keys = historical_name_keys(precinct_name)
            alias_vtds = expand_historical_alias_vtds(county, alias_keys, historical_aliases)
            for alias_vtd in alias_vtds:
                targets.extend(maintained_historical_targets.get((county, norm(alias_vtd, 6)), []))
                if chain is not None:
                    targets.extend(source_to_target.get((county, alias_vtd), []))
            if not targets and fallback_aliases is not None:
                fallback_vtds = expand_historical_alias_vtds(county, alias_keys, fallback_aliases)
                for alias_vtd in fallback_vtds:
                    targets.extend(fallback_source_to_target.get((county, alias_vtd), []))
        if not targets and year < 2008:
            source_name_key = name_key(precinct_name)
            for (proxy_county, proxy_source_vtd, proxy_name), proxy_targets in CHESTER_TABBLOCK_PROXY_TARGETS.items():
                if (
                    county == proxy_county
                    and source_vtd == proxy_source_vtd
                    and source_name_key == name_key(proxy_name)
                ):
                    targets.extend(proxy_targets)
                    break
        if not targets and year < 2008 and proxy_aliases is not None and proxy_chain is not None:
            proxy_vtds = expand_historical_alias_vtds(
                county,
                historical_name_keys(precinct_name),
                proxy_aliases,
            )
            if len(proxy_vtds) == 1:
                proxy_vtd = next(iter(proxy_vtds))
                targets.extend(
                    (row.dst_countyfp, row.dst_vtd, float(row.weight))
                    for row in proxy_chain.itertuples(index=False)
                    if row.countyfp == county and row.src_vtd == proxy_vtd
                )
        if not targets and geometry_targets:
            targets = geometry_targets.get(source_key, [])
        if not targets and year == 2006:
            alias_vtd = PA_2006_GEOMETRY_CODE_ALIASES.get((county, source_vtd))
            if alias_vtd:
                targets = geometry_targets.get((county, alias_vtd, ""), [])
        targets = normalize_vtd_targets(targets)
        if not targets:
            unmatched += 1
            unmatched_votes += sum(float(value or 0) for value in values.values())
            unmatched_keys.append(source_key)
            continue
        source_row_total = sum(float(value or 0) for value in values.values())
        for scope in selected_scopes:
            assigned_factor = sum(
                chain_weight * sum(weight for _district, weight in memberships[scope].get((county, vtd), []))
                for county, vtd, chain_weight in targets
            )
            gap = max(0.0, 1.0 - assigned_factor)
            if gap > 1e-9:
                membership_gap_votes[scope] += source_row_total * gap
                membership_gap_keys[scope].append([*source_key, gap])
        for county, vtd, chain_weight in targets:
            for scope in selected_scopes:
                for district, district_weight in memberships[scope].get((county, vtd), []):
                    factor = chain_weight * district_weight
                    for bucket in values:
                        district_votes[scope][district][bucket] += values[bucket] * factor

    for scope, votes in district_votes.items():
        allocated_total = sum(
            float(value or 0)
            for row in votes.values()
            for value in row.values()
        )
        # A crosswalk may legitimately leave a small number of source rows
        # unmatched, but it must never create votes.  This guard catches the
        # duplicated-target failure that previously inflated the 2012 CD 02
        # and CD 03 results before any application data is overwritten.
        tolerance = max(1.0, source_total * 1e-9)
        if allocated_total > source_total + tolerance:
            raise RuntimeError(
                f"{year} {contest} {scope} allocation created votes: "
                f"source={source_total:.3f}, allocated={allocated_total:.3f}, "
                f"excess={allocated_total - source_total:.3f}"
            )
        allocation_coverage = allocated_total / source_total if source_total > 0 else 1.0
        if allocation_coverage < 0.95:
            raise RuntimeError(
                f"{year} {contest} {scope} allocation coverage is too low: "
                f"source={source_total:.3f}, allocated={allocated_total:.3f}, "
                f"coverage={allocation_coverage:.2%}, unmatched_keys={unmatched}"
            )
        expected = expected_districts(scope)
        results = district_result_rows(votes, candidates)
        calibration_source = apply_dra_presidential_shares(scope, contest, year, results)
        exact_benchmark_source = apply_exact_district_benchmarks(scope, contest, year, results)
        statewide_control_source = apply_statewide_vote_control(contest, year, results)
        output = {
            "scope": scope,
            "contest_type": contest,
            "year": year,
            "meta": {
                "districts_observed": len(results),
                "districts_expected": len(expected),
                "coverage_percent": (len(set(results) & expected) / len(expected) * 100) if expected else 0.0,
                "source": (
                    f"precinct_returns_to_vtd_block_chain_{weight_mode}_districts"
                    + (f"+dra_share_calibration/{calibration_source}" if calibration_source else "")
                    + (f"+exact_district_benchmark/{exact_benchmark_source}" if exact_benchmark_source else "")
                    + (f"+statewide_vote_control/{statewide_control_source}" if statewide_control_source else "")
                ),
                "unmatched_source_vtds": unmatched,
                "unmatched_source_votes": unmatched_votes,
                "unmatched_source_keys": [list(key) for key in unmatched_keys],
                "district_membership_gap_votes": membership_gap_votes[scope],
                "district_membership_gap_keys": membership_gap_keys[scope],
            },
            "general": {"results": results},
        }
        path = out_dir / f"{scope}_{contest}_{year}.json"
        # The reviewed 2020 legislative files were produced from RDH's
        # block-level disaggregation. Do not silently replace them with a
        # lower-coverage precinct/VTD rebuild. This specifically guards the
        # split-district redistribution that removed roughly 14,700 votes.
        if year == 2020 and contest == "president" and scope in {"state_house", "state_senate"} and path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if "RDH 2020 general election results disaggregated" in existing.get("meta", {}).get("source", ""):
                existing_results = existing.get("general", {}).get("results", {})
                changed = []
                for district, existing_row in existing_results.items():
                    rebuilt_row = results.get(district)
                    if not rebuilt_row:
                        changed.append(district)
                        continue
                    delta = abs(int(rebuilt_row["total_votes"]) - int(existing_row["total_votes"]))
                    tolerance = max(5, round(int(existing_row["total_votes"]) * 0.0005))
                    if delta > tolerance:
                        changed.append(district)
                if changed:
                    raise RuntimeError(
                        f"Refusing to overwrite reviewed RDH 2020 {scope} turnout; "
                        f"material district changes in {len(changed)} districts"
                    )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path.relative_to(ROOT)} districts={len(results)} unmatched_source_vtds={unmatched}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", nargs="+", type=int, default=[2016, 2020])
    parser.add_argument("--contest", default="president")
    parser.add_argument("--office-code", default="USP")
    parser.add_argument("--out-dir", type=Path, default=DATA / "district_contests_crosswalk")
    parser.add_argument("--source-dir", type=Path, default=DATA)
    parser.add_argument(
        "--source-file",
        type=Path,
        help="Explicit raw precinct-return file; useful for legacy OpenElections files",
    )
    parser.add_argument("--district-weight-mode", choices=["area", "block_count"], default="area")
    parser.add_argument(
        "--block-vtd-source",
        type=Path,
        help="Optional block-to-VTD CSV, such as the PA adjusted 2021 geography crosswalk",
    )
    parser.add_argument(
        "--source-vtd-source",
        type=Path,
        help="Optional election VTD-code to Census VTD20 crosswalk from PA adjusted geography",
    )
    parser.add_argument(
        "--exception-source",
        type=Path,
        help="Optional explicit modern precinct exception crosswalk",
    )
    parser.add_argument("--county-precinct-source", type=Path, help="Official county precinct polygon-to-VTD20 crosswalk")
    parser.add_argument("--vest-crosswalk-source", type=Path, help="VEST 2018 precinct-to-VTD20 crosswalk")
    parser.add_argument("--scopes", nargs="+", choices=list(SCOPES), default=list(SCOPES))
    parser.add_argument(
        "--historical-vtd-source",
        type=Path,
        help="Historical VTD shapefile/zip with 2016 votes on VTD10 (avoids local precinct-ID mismatches)",
    )
    parser.add_argument(
        "--historical-geometry-source",
        type=Path,
        help="Historical PA precinct boundary shapefile whose GEOID10 suffix matches legacy election precinct IDs",
    )
    args = parser.parse_args()
    args.out_dir = args.out_dir.resolve()
    args.source_dir = args.source_dir.resolve()
    if args.block_vtd_source:
        args.block_vtd_source = args.block_vtd_source.resolve()
    if args.source_vtd_source:
        args.source_vtd_source = args.source_vtd_source.resolve()
    if args.exception_source:
        args.exception_source = args.exception_source.resolve()
    if args.county_precinct_source:
        args.county_precinct_source = args.county_precinct_source.resolve()
    if args.vest_crosswalk_source:
        args.vest_crosswalk_source = args.vest_crosswalk_source.resolve()
    for year in args.years:
        source = args.source_file.resolve() if args.source_file else args.source_dir / f"ElectionReturns_{year}_General_PrecinctReturns.txt"
        if not source.exists():
            raise FileNotFoundError(source)
        build_one(
            year,
            source,
            args.contest,
            args.office_code,
            args.out_dir,
            args.district_weight_mode,
            args.scopes,
            args.historical_vtd_source,
            args.historical_geometry_source,
            args.block_vtd_source,
            args.source_vtd_source,
            args.exception_source,
            args.county_precinct_source,
            args.vest_crosswalk_source,
        )


if __name__ == "__main__":
    main()

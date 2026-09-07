"""Build pre-2018 precinct-to-current-VTD20 crosswalks."""
from __future__ import annotations

import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "crosswalks" / "pa_historical_precinct_to_vtd20.csv"
sys.path.insert(0, str(ROOT / "Scripts"))
try:
    import regenerate_pa_district_jsons_from_crosswalks as r  # noqa: E402
except ModuleNotFoundError:
    r = None


def keys(value: str) -> set[str]:
    if r is None:
        return {re.sub(r"\s+", " ", str(value or "").upper()).strip()}
    raw = r.normalize_modern_precinct_name(value)
    out = set(r.historical_name_keys(raw)) | {r.compact_live_name(raw)}
    stripped = re.sub(r"^0*\d{1,5}[ _-]+", "", raw).strip()
    if stripped and stripped != raw:
        out |= set(r.historical_name_keys(stripped)) | {r.compact_live_name(stripped)}
    return {v for v in out if v}


# Allegheny labels that the older source files do not connect to a usable
# historic VTD code. These targets are carried back from the 2018 RDH
# block-derived crosswalk for the same named precincts. Split/consolidated
# labels are intentionally listed one by one rather than applied statewide.
_ALLEGHENY_EXCEPTION_ROWS = {
    (2008, "002000"): [("003", "001998", 1.0)],
    (2008, "002042"): [("003", "002043", 1.0)],
    (2008, "002045"): [("003", "002043", 1.0)],
    (2008, "OHIO D 3"): [("003", "005386", 1.0)],
    (2008, "SOUTH FAYETTE D 7"): [("003", "00F417", 1.0)],
    (2008, "SOUTH FAYETTE D 8"): [("003", "00F425", 1.0)],
    (2008, "SOUTH FAYETTE D 9"): [("003", "00F427", 1.0)],
    (2008, "SOUTH FAYETTE D 10"): [("003", "00F435", 1.0)],
    (2008, "SOUTH FAYETTE D 11"): [
        ("003", "00F395", 0.016033755274),
        ("003", "00F399", 0.011814345992),
        ("003", "00F437", 0.972151898734),
    ],
    (2008, "SOUTH FAYETTE D 12"): [("003", "00F445", 1.0)],
    (2012, "002000"): [("003", "001998", 1.0)],
    (2012, "002042"): [("003", "002043", 1.0)],
    (2012, "002045"): [("003", "002043", 1.0)],
    (2012, "WHITEHALL D 1 B (CONG 18)"): [("003", "00G740", 1.0)],
    (2016, "CORAOPOLIS WARD 2"): [("003", "001351", 1.0)],
    (2016, "ELIZABETH WARD 3"): [("003", "001998", 1.0)],
    (2016, "WHITEHALL DISTRICT 1 A"): [("003", "00G740", 1.0)],
    (2016, "WHITEHALL DISTRICT 1 B"): [("003", "00G740", 1.0)],
}

ALLEGHENY_EXCEPTIONS = {
    (year, key): targets
    for (year, label), targets in _ALLEGHENY_EXCEPTION_ROWS.items()
    for key in keys(label)
}


def apply_allegheny_exceptions() -> None:
    """Patch the known rows without rebuilding unrelated historical years."""
    with OUT.open(newline="", encoding="utf-8-sig") as handle:
        existing = list(csv.DictReader(handle))
    output = []
    replaced = set()
    for row in existing:
        year = int(row["year"])
        targets = []
        if row["countyfp"] == "003":
            for key in keys(row["source_precinct"]):
                targets = ALLEGHENY_EXCEPTIONS.get((year, key), [])
                if targets:
                    break
        exception_key = (year, row["countyfp"], row["source_precinct"])
        if not targets:
            output.append(row)
            continue
        if exception_key in replaced:
            continue
        replaced.add(exception_key)
        total = sum(weight for _, _, weight in targets) or 1.0
        for dst_county, dst_vtd, weight in targets:
            output.append({
                "year": year,
                "countyfp": row["countyfp"],
                "source_precinct": row["source_precinct"],
                "method": "allegheny_2018_block_name_fallback",
                "dst_countyfp": dst_county,
                "dst_vtd": dst_vtd,
                "weight": f"{weight / total:.12f}",
            })
    for (year, label), targets in _ALLEGHENY_EXCEPTION_ROWS.items():
        exception_key = (year, "003", label)
        if exception_key in replaced:
            continue
        total = sum(weight for _, _, weight in targets) or 1.0
        for dst_county, dst_vtd, weight in targets:
            output.append({
                "year": year,
                "countyfp": "003",
                "source_precinct": label,
                "method": "allegheny_2018_block_name_fallback",
                "dst_countyfp": dst_county,
                "dst_vtd": dst_vtd,
                "weight": f"{weight / total:.12f}",
            })
        replaced.add(exception_key)
    output.sort(key=lambda row: (int(row["year"]), row["countyfp"], row["source_precinct"], row["dst_countyfp"], row["dst_vtd"]))
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["year", "countyfp", "source_precinct", "method", "dst_countyfp", "dst_vtd", "weight"])
        writer.writeheader()
        writer.writerows(output)
    print(f"patched {len(replaced):,} Allegheny historical precinct mappings in {OUT}")


def block_targets(year: int) -> dict[tuple[str, str], list[tuple[str, str, float]]]:
    source = DATA / f"pa_{year}_gen_2020_blocks.zip"
    if not source.exists():
        return {}
    blocks = gpd.read_file(f"zip://{source.resolve().as_posix()}", columns=["GEOID20", "COUNTYFP", "PRECINCTID", "VAP_MOD"])
    blocks["block"] = blocks.GEOID20.map(lambda v: r.norm(v, 15))
    blocks["county"] = blocks.COUNTYFP.map(lambda v: r.norm(v, 3))
    blocks["vap"] = pd.to_numeric(blocks.VAP_MOD, errors="coerce").fillna(0.0)
    xwalk = pd.read_csv(DATA / "crosswalks/pa_block20_to_vtd20.csv", dtype=str)
    xwalk["block"] = xwalk.block.map(lambda v: r.norm(v, 15))
    xwalk["dst_county"] = xwalk.countyfp_dst.map(lambda v: r.norm(v, 3))
    xwalk["dst_vtd"] = xwalk.dst_vtd.map(lambda v: r.norm(v, 6))
    merged = blocks[["block", "county", "PRECINCTID", "vap"]].merge(xwalk[["block", "dst_county", "dst_vtd"]], on="block", how="inner")
    grouped = merged.groupby(["county", "PRECINCTID", "dst_county", "dst_vtd"], as_index=False).vap.sum()
    result = {}
    for (county, precinct), frame in grouped.groupby(["county", "PRECINCTID"], sort=False):
        total = float(frame.vap.sum()) or 1.0
        targets = [(row.dst_county, row.dst_vtd, float(row.vap) / total) for row in frame.itertuples(index=False)]
        for key in keys(precinct):
            result[(county, key)] = targets
    return result


def chain_targets(path: Path) -> dict[tuple[str, str], list[tuple[str, str, float]]]:
    frame = pd.read_csv(path, dtype=str)
    frame["county"] = frame["countyfp"].map(lambda v: r.norm(v, 3))
    frame["src_vtd"] = frame["src_vtd"].map(lambda v: r.norm(v, 6))
    frame["dst_county"] = frame["dst_countyfp" if "dst_countyfp" in frame else "countyfp_dst"].map(lambda v: r.norm(v, 3))
    frame["dst_vtd"] = frame.dst_vtd.map(lambda v: r.norm(v, 6))
    frame["weight"] = pd.to_numeric(frame.weight, errors="coerce").fillna(0.0)
    return {
        key: [(row.dst_county, row.dst_vtd, float(row.weight)) for row in group.itertuples(index=False)]
        for key, group in frame.groupby(["county", "src_vtd"], sort=False)
    }


def main() -> None:
    if r is None:
        raise RuntimeError(
            "full rebuild requires Scripts/regenerate_pa_district_jsons_from_crosswalks.py; "
            "use --apply-allegheny-exceptions for the targeted patch"
        )
    rows = []
    block_by_year = {2016: block_targets(2016)}
    chains = {
        "vtd00_block_chain": chain_targets(DATA / "crosswalks/pa_vtd00_to_vtd20_block_chain.csv"),
        "vtd10_block_chain": chain_targets(DATA / "crosswalks/pa_vtd10_to_vtd20_block_chain.csv"),
    }
    for year in range(2000, 2017, 2):
        source = next(DATA.joinpath("Openelections", str(year)).glob("*__pa__general__precinct.csv"))
        offices = set()
        with source.open(newline="", encoding="utf-8-sig") as handle:
            for raw in csv.reader(handle):
                if len(raw) > 8 and raw[8].strip(): offices.add(raw[8].strip().upper())
        if year == 2016:
            offices = {"PRESIDENT"}
        source_votes = {}
        for office in offices:
            parsed, _ = r.parse_precinct_returns(source, year, office)
            source_votes.update(parsed)
        chain = chains["vtd00_block_chain" if year <= 2006 else "vtd10_block_chain"]
        historical_aliases = r.read_historical_vtd_aliases(year)
        for county, source_vtd, name in sorted(source_votes):
            source_label = r.norm(source_vtd, 6) if year < 2016 and source_vtd != "000000" else name
            targets = []
            method = "unmatched"
            if year == 2016:
                for key in keys(name):
                    targets = block_by_year[2016].get((county, key), [])
                    if targets: break
                if targets: method = "rdh_precinct_blocks"
            if not targets and source_vtd != "000000":
                targets = chain.get((county, r.norm(source_vtd, 6)), [])
                if targets: method = "historical_vtd_block_chain"
            if not targets:
                historical_vtds = set()
                for key in keys(name):
                    historical_vtds.update(historical_aliases.get((county, key), set()))
                for historical_vtd in sorted(historical_vtds):
                    targets.extend(chain.get((county, r.norm(historical_vtd, 6)), []))
                if targets: method = "historical_name_to_vtd_block_chain"
            if not targets and county == "003":
                for key in keys(name):
                    targets = ALLEGHENY_EXCEPTIONS.get((year, key), [])
                    if targets:
                        method = "allegheny_2018_block_name_fallback"
                        break
            if not targets:
                rows.append({"year": year, "countyfp": county, "source_precinct": source_label, "method": method, "dst_countyfp": "", "dst_vtd": "", "weight": ""})
                continue
            collapsed = defaultdict(float)
            for dst_county, dst_vtd, weight in targets:
                collapsed[(dst_county, dst_vtd)] += float(weight)
            total = sum(collapsed.values()) or 1.0
            for (dst_county, dst_vtd), weight in sorted(collapsed.items()):
                rows.append({"year": year, "countyfp": county, "source_precinct": source_label, "method": method, "dst_countyfp": dst_county, "dst_vtd": dst_vtd, "weight": f"{weight / total:.12f}"})
    consolidated = {}
    methods_by_key = {}
    for row in rows:
        key = (row["year"], row["countyfp"], row["source_precinct"])
        methods_by_key.setdefault(key, set()).add(row["method"])
        if row["dst_vtd"]:
            target = (row["dst_countyfp"], row["dst_vtd"])
            consolidated.setdefault(key, {})[target] = consolidated.setdefault(key, {}).get(target, 0.0) + float(row["weight"] or 0.0)
        else:
            consolidated.setdefault(key, {})
    rows = []
    for (year, county, source), targets in sorted(consolidated.items()):
        method = "+".join(sorted(methods_by_key[(year, county, source)]))
        if not targets:
            rows.append({"year": year, "countyfp": county, "source_precinct": source, "method": method, "dst_countyfp": "", "dst_vtd": "", "weight": ""})
            continue
        total = sum(targets.values()) or 1.0
        for (dst_county, dst_vtd), weight in sorted(targets.items()):
            rows.append({"year": year, "countyfp": county, "source_precinct": source, "method": method, "dst_countyfp": dst_county, "dst_vtd": dst_vtd, "weight": f"{weight / total:.12f}"})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["year", "countyfp", "source_precinct", "method", "dst_countyfp", "dst_vtd", "weight"])
        writer.writeheader(); writer.writerows(rows)
    print(f"wrote {OUT} rows={len(rows):,}")


if __name__ == "__main__":
    if "--apply-allegheny-exceptions" in sys.argv:
        apply_allegheny_exceptions()
    else:
        main()

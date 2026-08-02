import csv
import os
import sys
import re
from pathlib import Path

import geopandas as gpd
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))
import regenerate_pa_district_jsons_from_crosswalks as r  # noqa: E402


SOURCES = {
    # Prefer PA's wide official returns because these preserve the election
    # VTD code.  The compact OpenElections exports often replace it with
    # 000000, forcing an avoidable name-only match.
    2018: (ROOT / "data/pa_official_2018_general_returns.txt", ["GOV", "USS"]),
    2020: (ROOT / "data/ElectionReturns_2020_General_PrecinctReturns.txt", ["USP", "ATT", "AUD", "TRE"]),
    2022: (ROOT / "data/pa_official_2022_general_returns.txt", ["GOV", "USS"]),
    2024: (ROOT / "data/pa_official_2024_general_returns.txt", ["USP", "USS", "ATT", "AUD", "TRE", "USC"]),
}


def main():
    output = ROOT / "data/crosswalks/pa_modern_precinct_to_vtd20.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    aliases = r.read_current_vtd_aliases()
    source_code_targets, source_name_targets = r.read_source_vtd_code_crosswalk(
        ROOT / "data/crosswalks/pa_adjusted_vtd_code_to_vtd20.csv"
    )
    county_precinct_targets = r.read_county_precinct_crosswalk(
        ROOT / "data/crosswalks/pa_county_precinct_to_vtd20.csv"
    )
    live_vtd_targets = r.read_live_vtd_crosswalk()
    exceptions = r.read_modern_exception_crosswalk(
        ROOT / "data/crosswalks/pa_modern_exception_vtds.csv"
    )
    vest_targets = r.read_vest_crosswalk(
        ROOT / "data/crosswalks/pa_vest18_to_vtd20_residual_counties.csv"
    )
    alias_resolution_cache = {}

    def block_name_keys(value):
        raw = r.normalize_modern_precinct_name(value)
        values = {raw, r.compact_live_name(raw)} if raw else set()
        stripped = re.sub(r"^0*\d{1,5}[ _-]+", "", raw).strip()
        if stripped and stripped != raw:
            values.update(r.historical_name_keys(stripped))
            values.add(r.compact_live_name(stripped))
        values.update(r.historical_name_keys(raw))
        return {value for value in values if value}

    def load_block_precinct_targets(year):
        # RDH-style files assign each 2020 Census block to the election-era
        # precinct that supplied the returns.  Aggregate those blocks into
        # current VTD20 targets using VAP_MOD as the disaggregation weight.
        source = ROOT / f"data/pa_{year}_gen_2020_blocks.zip"
        if not source.exists():
            return {}
        blocks = gpd.read_file(f"zip://{source.resolve().as_posix()}", columns=["GEOID20", "COUNTYFP", "PRECINCTID", "VAP_MOD"])
        blocks["block"] = blocks["GEOID20"].map(lambda value: r.norm(value, 15))
        blocks["countyfp"] = blocks["COUNTYFP"].map(lambda value: r.norm(value, 3))
        blocks["vap"] = pd.to_numeric(blocks["VAP_MOD"], errors="coerce").fillna(0.0)
        xwalk = pd.read_csv(ROOT / "data/crosswalks/pa_block20_to_vtd20.csv", dtype=str)
        xwalk["block"] = xwalk["block"].map(lambda value: r.norm(value, 15))
        xwalk["dst_countyfp"] = xwalk["countyfp_dst"].map(lambda value: r.norm(value, 3))
        xwalk["dst_vtd"] = xwalk["dst_vtd"].map(lambda value: r.norm(value, 6))
        merged = blocks[["block", "countyfp", "PRECINCTID", "vap"]].merge(
            xwalk[["block", "dst_countyfp", "dst_vtd"]], on="block", how="inner"
        )
        totals = merged.groupby(["countyfp", "PRECINCTID", "dst_countyfp", "dst_vtd"], as_index=False)["vap"].sum()
        totals = totals[totals["vap"] > 0].copy()
        result = {}
        for (county, precinct), group in totals.groupby(["countyfp", "PRECINCTID"], sort=False):
            weights = group.groupby(["dst_countyfp", "dst_vtd"], as_index=False)["vap"].sum()
            total = float(weights["vap"].sum()) or 1.0
            targets = [(row.dst_countyfp, row.dst_vtd, float(row.vap) / total) for row in weights.itertuples(index=False)]
            for key in block_name_keys(precinct):
                result.setdefault((county, key), targets)
        return result

    block_precinct_targets = {year: load_block_precinct_targets(year) for year in (2018, 2020)}
    for year, (source_file, offices) in SOURCES.items():
        source_votes = {}
        for office in offices:
            votes, _ = r.parse_precinct_returns(source_file, year, office)
            source_votes.update(votes)
        geometry = {}
        geometry_years = {
            int(value.strip()) for value in os.environ.get("PA_CROSSWALK_GEOMETRY_YEARS", "").split(",")
            if value.strip().isdigit()
        }
        use_geometry = os.environ.get("PA_CROSSWALK_SKIP_GEOMETRY") != "1" and (
            not geometry_years or year in geometry_years
        )
        if use_geometry:
            geometry = r.read_historical_geometry_targets(
                year,
                source_votes.keys(),
                ROOT / "data/pa_election_geodata_2011_boundaries/2011 Voting District Boundary Shapefiles/VTDS.shp",
            )
        for county, source_vtd, precinct_name in sorted(source_votes):
            targets = []
            method = "unmatched"
            source_code = r.norm(source_vtd, 6)
            source_name = r.normalize_modern_precinct_name(precinct_name)

            block_targets = []
            block_index = block_precinct_targets.get(year, {})
            for key in block_name_keys(source_name):
                if (county, key) in block_index:
                    block_targets = block_index[(county, key)]
                    break
            if block_targets:
                targets = list(block_targets)
                method = "rdh_precinct_blocks"

            # Prefer the adjusted PA geography/code bridge.  The prior builder
            # treated the election export's source code as a VTD20 code, which
            # silently produced false direct matches for legacy/current code
            # systems and left name-only rows unresolved.
            adjusted_vtd = source_code_targets.get((county, source_code)) if not targets else None
            if adjusted_vtd:
                targets = [(county, adjusted_vtd, 1.0)]
                method = "adjusted_vtd_code"
            if not targets:
                name_keys = r.historical_name_keys(source_name)
                name_vtds = set()
                for key in name_keys:
                    name_vtds.update(source_name_targets.get((county, key), set()))
                if name_vtds:
                    targets = [(county, vtd, 1.0) for vtd in sorted(name_vtds)]
                    method = "adjusted_vtd_name"
            if not targets:
                county_targets = county_precinct_targets.get((county, r.compact_live_name(source_name)), [])
                if county_targets:
                    targets = [(county, vtd, weight) for vtd, weight in county_targets]
                    method = "official_county_precinct"
            if not targets and year == 2018:
                vest = vest_targets.get((county, source_code), []) or vest_targets.get((county, r.compact_live_name(source_name)), [])
                if vest:
                    targets = [(county, vtd, weight) for vtd, weight in vest]
                    method = "vest18_area"
            if not targets:
                exception_vtds = exceptions.get((year, county, source_code, precinct_name), set())
                if exception_vtds:
                    targets = [(county, vtd, 1.0) for vtd in sorted(exception_vtds)]
                    method = "modern_exception"
            if not targets and source_code != "000000":
                live_targets = live_vtd_targets.get((county, source_code), [])
                if live_targets:
                    targets = [(dst_county, dst_vtd, weight) for dst_county, dst_vtd, weight in live_targets]
                    method = "live_vtd_chain"
            if not targets:
                alias_key = (county, source_name)
                if alias_key not in alias_resolution_cache:
                    alias_resolution_cache[alias_key] = r.resolve_current_alias_vtds(county, source_name, aliases)
                alias_vtds = alias_resolution_cache[alias_key]
                if alias_vtds:
                    targets = [(county, vtd, 1.0) for vtd in sorted(alias_vtds)]
                    method = "current_vtd_name"
            if not targets:
                targets = geometry.get((county, source_vtd, precinct_name), [])
                if targets:
                    method = "historical_geometry"
            if not targets:
                rows.append({"year": year, "countyfp": county, "source_precinct": precinct_name, "method": method, "dst_countyfp": "", "dst_vtd": "", "weight": ""})
                continue
            # Several source bridges can represent the same target more than
            # once (for example a padded and unpadded VTD key). Collapse those
            # duplicates and normalize every source precinct to one total.
            collapsed = {}
            for dst_county, dst_vtd, weight in targets:
                key = (r.norm(dst_county, 3), r.norm(dst_vtd, 6))
                collapsed[key] = collapsed.get(key, 0.0) + float(weight)
            total_weight = sum(collapsed.values()) or 1.0
            for (dst_county, dst_vtd), weight in sorted(collapsed.items()):
                rows.append({"year": year, "countyfp": county, "source_precinct": precinct_name, "method": method, "dst_countyfp": dst_county, "dst_vtd": dst_vtd, "weight": f"{weight / total_weight:.12f}"})
        print(year, "source_precincts", len(source_votes), "rows", sum(1 for row in rows if row["year"] == year), "unmatched", sum(1 for row in rows if row["year"] == year and not row["dst_vtd"]))
    # The browser crosswalk is keyed by source precinct name. Official files
    # can carry multiple VTD-coded rows under that same name, so consolidate
    # those rows before writing and renormalize the combined target weights.
    consolidated = {}
    methods_by_key = {}
    for row in rows:
        key = (row["year"], row["countyfp"], row["source_precinct"])
        if not row["dst_vtd"]:
            consolidated.setdefault(key, {})
            methods_by_key.setdefault(key, set()).add(row["method"])
            continue
        target_key = (row["dst_countyfp"], row["dst_vtd"])
        consolidated.setdefault(key, {})[target_key] = consolidated.setdefault(key, {}).get(target_key, 0.0) + float(row["weight"] or 0.0)
        methods_by_key.setdefault(key, set()).add(row["method"])
    rows = []
    for key in sorted(consolidated):
        year, county, source = key
        targets = consolidated[key]
        method = "+".join(sorted(methods_by_key.get(key, set())))
        if not targets:
            rows.append({"year": year, "countyfp": county, "source_precinct": source, "method": method or "unmatched", "dst_countyfp": "", "dst_vtd": "", "weight": ""})
            continue
        total = sum(targets.values()) or 1.0
        for (dst_county, dst_vtd), weight in sorted(targets.items()):
            rows.append({"year": year, "countyfp": county, "source_precinct": source, "method": method, "dst_countyfp": dst_county, "dst_vtd": dst_vtd, "weight": f"{weight / total:.12f}"})
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["year", "countyfp", "source_precinct", "method", "dst_countyfp", "dst_vtd", "weight"])
        writer.writeheader()
        writer.writerows(rows)
    print("wrote", output, "rows", len(rows))


if __name__ == "__main__":
    main()

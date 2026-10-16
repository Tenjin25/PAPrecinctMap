"""Diagnostic benchmark source-row, VTD, and block ledgers; no production writes."""
import csv
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Scripts"))
sys.path.insert(0, str(ROOT))
import build_county_clustered_2024_district_contests as clustered
import build_rdh_2024_district_contests as rdh
import build_pa_data_layers as layers

OUT = Path(__file__).resolve().parent / "benchmark_ledgers"


def save(name, rows):
    rows = list(rows)
    with (OUT / name).open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["status"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(exist_ok=True)
    data = ROOT / "data"
    maps, counties, _, _ = clustered.build_vap_maps(data / "crosswalks/pa_block20_vap.csv.gz", data / "BlockAssign_ST42_PA.zip")
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    layers.load_vtd_current_district_blocks = lambda: maps
    summary = {}
    for year, district, prefix in ((2024, "8", "pa08"), (2018, "10", "pa10")):
        source = next(path for y, path in layers.iter_openelections_csvs() if y == year)
        rows = clustered.integerize_fractional_rows(layers.read_csv_rows(source))
        rows = layers.apply_official_county_party_controls(rows, year, contest_types={"us_senate"})
        ledger, matching, vtd_totals = [], {}, defaultdict(float)
        totals = defaultdict(int)
        affected_vtds = set()
        for index, row in enumerate(rows):
            if layers.office_mapping_for_contest(row.get("office", "")) != "us_senate":
                continue
            votes = layers.safe_int(row.get("votes"))
            if votes <= 0:
                continue
            county = layers.normalize_county_name(row.get("county", ""))
            fp = layers.county_fips_by_name().get(county, "")
            key = (fp, row.get("precinct", ""), row.get("source_vtd", ""))
            if key not in matching:
                targets = layers.maintained_targets_for_row(row, year, fp)
                targets = [target for target in targets if maps["congressional"].get((target[0], target[1]))]
                if not targets:
                    targets = [(c, v, 1.0, "current_precinct_or_vtd_name") for c, v in layers.match_row_to_current_vtds(row)]
                weights = defaultdict(float)
                for c, v, share, method in targets:
                    for d, weight in maps["congressional"].get((c, v), {}).items():
                        weights[d] += share * weight
                matching[key] = (targets, weights)
            targets, weights = matching[key]
            allocation = layers.allocate_votes_by_block_counts(votes, weights)
            allocated = allocation.get(district, 0)
            if not weights.get(district):
                continue
            party = row.get("party", "").upper()
            bucket = "dem_votes" if party in layers.PARTY_DEM else "rep_votes" if party in layers.PARTY_REP else "other_votes"
            totals[bucket] += allocated
            ledger.append({"source_row_index": index, "county": county, "precinct": row.get("precinct", ""),
                           "source_vtd": row.get("source_vtd", ""), "party": party, "candidate": row.get("candidate", ""),
                           "votes_after_integerization_and_county_control": votes, "district_votes": allocated,
                           "district_weight": weights.get(district, 0), "all_district_weights": sum(weights.values()),
                           "weighted_vtds": json.dumps(targets), "all_district_allocations": json.dumps(allocation),
                           "mail_label": any(token in row.get("precinct", "").upper() for token in ("MAIL", "ABSENT", "PROVISION"))})
            denominator = sum(weights.values())
            for c, v, share, method in targets:
                affected_vtds.add((c, v))
                contribution = votes * share * maps["congressional"].get((c, v), {}).get(district, 0) / denominator
                vtd_totals[(c, v, bucket, method)] += contribution
        expected = json.loads((data / "district_bef_candidate" / f"congressional_us_senate_{year}.json").read_text())["general"]["results"][district]
        assert all(totals[field] == expected[field] for field in totals), (year, totals, expected)
        save(prefix + "_source_rows.csv", ledger)
        save(prefix + "_vtd_fractional_contributions.csv", [
            {"countyfp": c, "vtd": v, "party_bucket": bucket, "method": method, "fractional_contribution_before_row_rounding": votes}
            for (c, v, bucket, method), votes in sorted(vtd_totals.items())])
        vap = clustered.load_block_vap(data / "crosswalks/pa_block20_vap.csv.gz")
        baf = clustered.load_carter_vtds(data / "BlockAssign_ST42_PA.zip")
        assignments = clustered.load_district_assignments()
        blocks = [{"block": block, "countyfp": c, "vtd": v, "vap": vap[block],
                   **{scope: values[block] for scope, values in assignments.items()}}
                  for block, (c, v) in baf.items() if (c, v) in affected_vtds]
        save(prefix + "_block_assignments.csv", blocks)
        summary[prefix] = {"year": year, "district": district, "source": str(source),
                           "totals": dict(totals), "rows": len(ledger), "blocks": len(blocks),
                           "mail_label_rows": sum(row["mail_label"] for row in ledger)}

    archive = ROOT.parents[1] / "data/pa_2024_gen_prec_csv.zip"
    rows, statewide, columns = rdh.read_source(archive, 2024)
    # Reproduce the published county-clustered path, preserving fractional row
    # contributions until the builder's final district-level integerization.
    published_rows, county_sums = [], defaultdict(float)
    for row in rows:
        fp = row.get("COUNTYFP", "").zfill(3)
        if fp not in {"069", "079", "089", "103", "127"}:
            continue
        geometry, method = rdh.geometry_allocations(row, maps, 2024)
        material = counties["congressional"][fp]
        weights = {next(iter(material)): 1} if len(material) == 1 else geometry["congressional"]
        if not weights.get("8"):
            continue
        for column, info in statewide.items():
            if info["contest"] != "us_senate":
                continue
            votes = rdh.value(row, column)
            contribution = rdh.allocate(votes, weights).get("8", 0)
            bucket = "dem_votes" if info["party"] == "DEM" else "rep_votes" if info["party"] == "REP" else "other_votes"
            county_sums[(row["County"], bucket)] += contribution
            published_rows.append({"unique_id": row["UNIQUE_ID"], "county": row["County"],
                                   "election_precinct": row["Muni_Name"], "source_vtd": row["VTD code"],
                                   "candidate_column": column, "party_bucket": bucket, "source_votes": votes,
                                   "district_fractional_votes": contribution, "district_weights": json.dumps(weights),
                                   "method": "whole_county" if len(material) == 1 else method})
    save("pa08_published_election_precinct_rows.csv", published_rows)
    save("pa08_published_fractional_counties.csv", [{"county": county, "party_bucket": bucket, "votes": votes}
                                                   for (county, bucket), votes in sorted(county_sums.items())])
    final = {field: sum(value for (county, bucket), value in county_sums.items() if bucket == field)
             for field in ("dem_votes", "rep_votes", "other_votes")}
    summary["published_pa08_fractional_totals"] = final
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

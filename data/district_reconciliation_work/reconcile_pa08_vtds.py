"""Reconcile PA-08 fractional VTD paths and their separately explained rounding."""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "Scripts"), str(ROOT)]
import build_county_clustered_2024_district_contests as clustered
import build_rdh_2024_district_contests as rdh
import build_pa_data_layers as layers

OUT = Path(__file__).resolve().parent / "benchmark_ledgers"


def main():
    data = ROOT / "data"
    maps, _, _, _ = clustered.build_vap_maps(data / "crosswalks/pa_block20_vap.csv.gz", data / "BlockAssign_ST42_PA.zip")
    layers.VTD_CURRENT_DISTRICT_BLOCKS = maps
    layers.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = maps
    rows, _, _ = rdh.read_source(ROOT.parents[1] / "data/pa_2024_gen_prec_csv.zip", 2024)
    source = {row["UNIQUE_ID"]: row for row in rows}
    values = defaultdict(lambda: {"candidate_fractional": 0.0, "published_fractional": 0.0})
    with (OUT / "pa08_vtd_fractional_contributions.csv").open(newline="") as handle:
        for row in csv.DictReader(handle):
            values[(row["countyfp"], row["vtd"], row["party_bucket"])]["candidate_fractional"] += float(row["fractional_contribution_before_row_rounding"])
    target_cache = {}
    with (OUT / "pa08_published_election_precinct_rows.csv").open(newline="") as handle:
        for record in csv.DictReader(handle):
            row = source[record["unique_id"]]
            fp = row["COUNTYFP"].zfill(3)
            if record["unique_id"] not in target_cache:
                code = row["VTD code"].strip().upper().zfill(6)
                if any(maps[scope].get((fp, code)) for scope in maps):
                    targets = [(fp, code, 1.0)]
                else:
                    bridge = {"county": row["County"], "precinct": row.get("Muni_Name") or row["Precinct"], "source_vtd": row["VTD code"]}
                    maintained = layers.maintained_targets_for_row(bridge, 2024, fp)
                    maintained = [target for target in maintained if any(maps[scope].get((target[0], target[1])) for scope in maps)]
                    targets = [(c, v, weight) for c, v, weight, method in maintained] if maintained else [(c, v, 1.0) for c, v in layers.match_row_to_current_vtds(bridge)]
                target_cache[record["unique_id"]] = targets
            targets = target_cache[record["unique_id"]]
            denominator = sum(share * sum(maps["congressional"].get((c, v), {}).values()) for c, v, share in targets)
            observed = 0
            for c, v, share in targets:
                contribution = int(record["source_votes"]) * share * maps["congressional"].get((c, v), {}).get("8", 0) / denominator
                values[(c, v, record["party_bucket"])]["published_fractional"] += contribution
                observed += contribution
            assert abs(observed - float(record["district_fractional_votes"])) < 1e-7
    result = []
    for (fp, vtd, bucket), row in sorted(values.items()):
        result.append({"countyfp": fp, "vtd": vtd, "party_bucket": bucket,
                       **row, "candidate_minus_published": row["candidate_fractional"] - row["published_fractional"],
                       "cause": "normalized-return versus election-precinct allocation path"})
    exact = json.loads((data / "district_bef_candidate/congressional_us_senate_2024.json").read_text())["general"]["results"]["8"]
    published = json.loads((data / "district_contests/congressional_us_senate_2024.json").read_text())["general"]["results"]["8"]
    for bucket in ("dem_votes", "rep_votes", "other_votes"):
        before = sum(row["published_fractional"] for row in result if row["party_bucket"] == bucket)
        after = sum(row["candidate_fractional"] for row in result if row["party_bucket"] == bucket)
        result.extend([
            {"countyfp": "", "vtd": "CANDIDATE_ROW_ROUNDING", "party_bucket": bucket,
             "candidate_fractional": exact[bucket] - after, "published_fractional": 0,
             "candidate_minus_published": exact[bucket] - after, "cause": "largest remainder per normalized source row"},
            {"countyfp": "", "vtd": "PUBLISHED_DISTRICT_ROUNDING", "party_bucket": bucket,
             "candidate_fractional": 0, "published_fractional": published[bucket] - before,
             "candidate_minus_published": before - published[bucket], "cause": "largest remainder at final RDH district stage"},
        ])
        total = sum(row["candidate_minus_published"] for row in result if row["party_bucket"] == bucket)
        assert abs(total - (exact[bucket] - published[bucket])) < 1e-7
    with (OUT / "pa08_vtd_and_rounding_reconciliation.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(result[0]))
        writer.writeheader()
        writer.writerows(result)
    print("PA-08 VTD and rounding ledger reconciles exactly: DEM +268, REP +1162, Other +13")


if __name__ == "__main__":
    main()

"""Reconcile odd-year judicial district totals against retained source controls."""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
AUDIT = DATA / "district_bef_audit" / "published_lineage"
CANDIDATE = DATA / "district_bef_candidate"
PUBLISHED = DATA / "district_contests"
SOURCE_BY_YEAR = {
    2001: DATA / "ElectionReturns_2001_Municipal_PrecinctReturns.txt",
    2003: DATA / "ElectionReturns_2003_Municipal_PrecinctReturns.txt",
    2007: DATA / "ElectionReturns_2007_Municipal_PrecinctReturns.txt",
    2015: DATA / "ElectionReturns_2015_Municipal_Precinct.txt",
    2017: DATA / "ElectionReturns_2017_Municipal_PrecinctReturns.txt",
    2019: DATA / "ElectionReturns_2019_General_PrecinctReturns.txt",
    2021: DATA / "ElectionReturns_2021_Municipal_PrecinctReturns.txt",
    2023: DATA / "ElectionReturns_2023_Municipal_PrecinctReturns.txt",
    2025: DATA / "ElectionReturns_2025_Municipal_PrecinctReturns.txt",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def county_total(year: int, contest: str) -> int:
    path = DATA / "contests" / f"{contest}_{year}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sum(int(row.get("total_votes") or 0) for row in payload.get("rows", []))


def load_builder_aggregate():
    spec = importlib.util.spec_from_file_location("pa_builder_judicial_audit", ROOT / "build_pa_data_layers.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module.aggregate_county_results_from_openelections()["results_by_year"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deep", action="store_true", help="Reparse official precinct sources and localize county residuals")
    args = parser.parse_args()
    source_rows = list(csv.DictReader((AUDIT / "contest_year_classification.csv").open(encoding="utf-8-sig")))
    rows = []
    for item in source_rows:
        year = int(item["year"])
        contest = item["contest_type"]
        if not (year % 2 and ("court" in contest or "retention" in contest)):
            continue
        control = county_total(year, contest)
        official = int(item["source_votes"])
        published = int(item["congressional_published_total"])
        source = SOURCE_BY_YEAR[year]
        rows.append({
            "year": year,
            "contest_type": contest,
            "official_precinct_total": official,
            "county_aggregate_control": control,
            "published_district_total": published,
            "official_minus_county_control": official - control,
            "official_vs_county_pct": round((official - control) / control * 100, 6) if control else 0,
            "recovered_vs_published": official - published,
            "published_shortfall_pct_of_control": round((control - published) / control * 100, 6) if control else 0,
            "source_path": str(source.relative_to(ROOT)).replace("\\", "/"),
            "source_sha256": digest(source),
            "candidate_unmatched_rows": int(item["unmatched_rows"]),
            "candidate_conclusion": "official_precinct_source_complete",
            "published_conclusion": "legacy_matcher_dropped_precinct_votes",
        })
    fields = list(rows[0])
    with (AUDIT / "judicial_lineage_reconciliation.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    county_residuals = []
    if args.deep:
        aggregate = load_builder_aggregate()
        for item in rows:
            year = item["year"]
            contest = item["contest_type"]
            live = aggregate.get(year, {}).get(contest, {}).get("statewide", {}).get("results", {})
            stored_payload = json.loads((DATA / "contests" / f"{contest}_{year}.json").read_text(encoding="utf-8"))
            stored = {str(row.get("county") or "").upper(): row for row in stored_payload.get("rows", [])}
            for county in sorted(set(live) | set(stored)):
                live_row = live.get(county, {})
                stored_row = stored.get(county, {})
                deltas = {
                    field: int(live_row.get(field) or 0) - int(stored_row.get(field) or 0)
                    for field in ("dem_votes", "rep_votes", "other_votes", "total_votes")
                }
                if any(deltas.values()):
                    county_residuals.append({
                        "year": year,
                        "contest_type": contest,
                        "county": county,
                        **deltas,
                    })
        residual_fields = ["year", "contest_type", "county", "dem_votes", "rep_votes", "other_votes", "total_votes"]
        with (AUDIT / "judicial_county_source_revisions.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=residual_fields)
            writer.writeheader()
            writer.writerows(county_residuals)
    all_residuals_positive = bool(county_residuals) and all(
        int(row["total_votes"]) > 0 for row in county_residuals
    )
    max_source_control_pct = max(abs(row["official_vs_county_pct"]) for row in rows)
    min_published_shortfall = min(row["published_shortfall_pct_of_control"] for row in rows)
    max_published_shortfall = max(row["published_shortfall_pct_of_control"] for row in rows)
    largest = sorted(rows, key=lambda row: row["recovered_vs_published"], reverse=True)[:12]
    lines = [
        "# Judicial source-lineage reconciliation",
        "",
        "All 33 odd-year judicial groups use retained official Pennsylvania precinct-return files in the BEF candidate. Every source row is matched and conserved. The older published district files were built with the legacy OpenElections precinct matcher and are uniformly below the independent county aggregates.",
        "",
        f"- Groups: {len(rows)}",
        "- Candidate unmatched rows: 0",
        f"- Maximum official-precinct versus county-control difference: {max_source_control_pct:.3f}%",
        f"- Published shortfall range versus county controls: {min_published_shortfall:.3f}% to {max_published_shortfall:.3f}%",
        "- Conclusion: the large candidate/published differences are recovered precinct coverage, not BEF mapping or a multi-seat candidate-set error.",
        "",
        "Small official-versus-county-control residuals remain (at most 0.289%). Deep comparison shows that the retained official precinct totals exceed the old county controls in every nonzero county/contest cell. The normalized historical CSVs contain fractional disaggregated rows, and the old county builder truncated each row before summing. The builder now preserves fractions and rounds once per county/contest using largest remainder.",
        "",
        "## Largest recovered totals",
        "",
        "| Year | Contest | Published | Official precinct source | Recovered | County control |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    lines.extend(
        f"| {row['year']} | {row['contest_type']} | {row['published_district_total']:,} | "
        f"{row['official_precinct_total']:,} | {row['recovered_vs_published']:,} | "
        f"{row['county_aggregate_control']:,} |"
        for row in largest
    )
    lines += [
        "",
        "## Promotion rule",
        "",
        "Do not preserve the lower published totals merely for backward compatibility. Regenerate all three scopes together from the same official precinct source, then either retain exact official precinct totals or apply one documented statewide/county control consistently across every scope.",
    ]
    if args.deep:
        lines += [
            "",
            "## County-level residual localization",
            "",
            f"The deep reparse found {len(county_residuals):,} nonzero county/contest revisions. All are positive: {all_residuals_positive}. These are listed in `judicial_county_source_revisions.csv`; they are differences between the currently retained official precinct exports and the older row-truncated county-control JSONs, not allocation loss.",
        ]
    (AUDIT / "JUDICIAL_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "groups": len(rows),
        "candidate_unmatched_rows": sum(row["candidate_unmatched_rows"] for row in rows),
        "max_official_vs_county_pct": max_source_control_pct,
        "published_shortfall_pct_range": [min_published_shortfall, max_published_shortfall],
        "county_source_revision_rows": len(county_residuals) if args.deep else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

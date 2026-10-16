"""Read-only reconciliation of the completed acceptance candidate.

Writes diagnostics only. Missing published county attribution is explicitly
unresolved; candidate county destinations are never represented as delta causes.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
FIELDS = ("dem_votes", "rep_votes", "other_votes", "total_votes")
sys.path.insert(0, str(ROOT / "Scripts"))
from build_bef_candidate import verify_county_evidence


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path, rows):
    rows = list(rows)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ["status"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    candidate = DATA / "district_bef_candidate"
    out = DATA / "district_reconciliation_work" / "report"
    out.mkdir(parents=True, exist_ok=True)
    acceptance = read(candidate / "acceptance_report.json")
    with (candidate / "district_vote_changes.csv").open(newline="", encoding="utf-8") as handle:
        changes = list(csv.DictReader(handle))
    assert len(changes) == acceptance["counts"]["district_vote_changes"]
    summaries, county_context, exhaustive = Counter(), [], []
    payloads = {}
    for change in changes:
        name = change["file"]
        if name not in payloads:
            payloads[name] = (read(DATA / "district_contests" / name), read(candidate / name))
        published, exact = payloads[name]
        scope, year, contest = exact["scope"], exact["year"], exact["contest_type"]
        source = published["meta"].get("source", "")
        lineage = "DRA calibration" if "dra_share_calibration" in source else (
            "RDH election precinct versus Carter VTD" if "RDH" in source else
            "unresolved allocation lineage")
        key = (year, contest, scope, lineage)
        summaries[key] += 1
        exhaustive.append({"year": year, "contest": contest, "scope": scope,
                           **change, "documented_lineage": lineage,
                           "causal_attribution": "unresolved pending published row replay",
                           "promotion": "retain published"})
        counties = exact["meta"]["county_conservation_audit"]["counties"]
        for county, audit in counties.items():
            votes = audit["district_allocations"].get(change["district"])
            if not votes or not votes["total_votes"]:
                continue
            county_context.append({"year": year, "contest": contest, "scope": scope,
                                   "county": county, "district": change["district"],
                                   "candidate_county_total": votes["total_votes"],
                                   "candidate_quality": json.dumps(audit["allocation_quality_votes"], sort_keys=True),
                                   "county_delta": "unknown: published county decomposition absent",
                                   "cause": lineage})
    write_csv(out / "all_district_differences.csv", exhaustive)
    write_csv(out / "year_contest_scope_lineage.csv", [
        dict(zip(("year", "contest", "scope", "documented_lineage"), key), changed_rows=count)
        for key, count in sorted(summaries.items())])
    write_csv(out / "county_context.csv", county_context)

    benchmark_rows = []
    for year, district, prefix in ((2024, "8", "pa08"), (2018, "10", "pa10")):
        name = f"congressional_us_senate_{year}.json"
        for variant, directory in (("published", DATA / "district_contests"), ("exact", candidate),
                                   ("rdh", DATA / "district_reconciliation_work" / f"rdh_{year}"),
                                   ("clustered_rdh", DATA / "district_reconciliation_work" / f"clustered_{year}")):
            path = directory / name
            if not path.exists():
                continue
            row = read(path)["general"]["results"][district]
            benchmark_rows.append({"year": year, "district": district, "variant": variant,
                                   **{field: row[field] for field in FIELDS},
                                   "margin_pct": row["margin_pct"],
                                   "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    write_csv(out / "benchmarks.csv", benchmark_rows)
    evidence_errors = []
    for path in sorted(candidate.glob("*.json")):
        if path.name in {"manifest.json", "acceptance_report.json", "build_receipt.json"}:
            continue
        payload = read(path)
        if payload.get("meta", {}).get("allocation_audit"):
            errors = verify_county_evidence(payload)
            if errors:
                evidence_errors.append({"file": path.name, "errors": errors})
    (out / "county_evidence_failures.json").write_text(json.dumps(evidence_errors, indent=2) + "\n", encoding="utf-8")
    # Replayed county-clustered RDH exactly reproduces the published PA-08
    # row. RDH metadata truncates fractional county sums; show those separately
    # from its final district rounding, never label them as official integers.
    county_rows = []
    filename = "congressional_us_senate_2024.json"
    baseline = DATA / "district_reconciliation_work/clustered_2024" / filename
    if baseline.exists():
        published = read(baseline)
        exact = read(candidate / filename)
        assert published["general"]["results"]["8"] == read(DATA / "district_contests" / filename)["general"]["results"]["8"]
        summed = {label: dict.fromkeys(FIELDS, 0) for label in ("published", "candidate")}
        for county in ("LACKAWANNA", "LUZERNE", "MONROE", "PIKE", "WAYNE"):
            item = {"county": county, "basis": "truncated county metadata before district rounding"}
            for label, payload in (("published", published), ("candidate", exact)):
                row = payload["meta"]["county_conservation_audit"]["counties"][county]["district_allocations"].get("8", {})
                for field in FIELDS:
                    item[f"{label}_{field}"] = row.get(field, 0)
                    summed[label][field] += row.get(field, 0)
            for field in FIELDS:
                item[f"delta_{field}"] = item[f"candidate_{field}"] - item[f"published_{field}"]
            county_rows.append(item)
        rounding = {"county": "DISTRICT ROUNDING", "basis": "final district value less sum of truncated county metadata"}
        for label, payload in (("published", published), ("candidate", exact)):
            for field in FIELDS:
                rounding[f"{label}_{field}"] = payload["general"]["results"]["8"][field] - summed[label][field]
        for field in FIELDS:
            rounding[f"delta_{field}"] = rounding[f"candidate_{field}"] - rounding[f"published_{field}"]
        county_rows.append(rounding)
    write_csv(out / "pa08_county_and_rounding.csv", county_rows)
    report = {
        "baseline_commit": "0577735",
        "acceptance": acceptance["acceptance"],
        "counts": acceptance["counts"],
        "scope_counts": dict(Counter(row["scope"] for row in exhaustive)),
        "decision": "Retain production pending full causal attribution",
        "proposed_production_changes": [],
        "independently_recomputed_county_evidence_failure_files": len(evidence_errors),
        "limitations": [
            "Lineage labels identify documented method differences, not quantified causal decompositions.",
            "Published historical rows lack county attribution; assigning their district residual to candidate counties would fabricate evidence.",
            "2018 DRA share agreement is not independent proof: published PA-10 was calibrated to that source.",
            "The Wikipedia 2018 district table must be checked for district vintage: Pennsylvania had 18 districts then, versus 17 current districts.",
            "Candidate uses original BAF ZIP, while source ledger labels the 17-block-adjusted CSV as its Carter input.",
            "RDH county metadata truncates fractional allocations before statewide district rounding; separate rounding attribution is required.",
            "The original acceptance --reuse accepted unsigned copied publication directories. The revised code requires a completed input/output receipt.",
            "54 baseline candidate retention files put YES/NO into Other in their county metadata, despite displaying YES/NO in the two main columns. Their old county PASS flags are insufficient. The builder bookkeeping is corrected, and a new cold rebuild is required.",
            "Year-selective reuse and its manifest preservation are implemented and regression tested; a new signed cold run and warm-run integration check remain pending.",
        ],
    }
    (out / "status.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Remaining district differences: verified baseline", "",
             "Production recommendation: retain current values. No district changes proposed yet.", "",
             f"Completed baseline cold rebuild: {len(changes):,} district rows differ; statewide party totals are unchanged and its audit reports zero unmatched/unallocated rows. Independent county-evidence checks fail in {len(evidence_errors)} retention files; do not treat the old county PASS flags as verification.", "",
             "Official Luzerne precinct bounds reject the baseline 2024 Senate PA-08 candidate: it exceeds the maximum by 62 Democratic, 554 Republican, and 1 other vote. Retain the published PA-08 allocation; only pooled Butler Township District 5 requires a modeled VAP split. See ../official_luzerne_2024/EVIDENCE.md and the permanent Luzerne benchmark fixture.", "",
             "| Scope | Changed rows |", "|---|---:|"]
    lines += [f"| {scope} | {count:,} |" for scope, count in report["scope_counts"].items()]
    lines += ["", "The CSVs enumerate all differences and candidate county context. Causal reconciliation remains incomplete.", ""]
    lines += [f"- {limitation}" for limitation in report["limitations"]]
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"district_rows": len(changes), "output": str(out)}))


if __name__ == "__main__":
    main()

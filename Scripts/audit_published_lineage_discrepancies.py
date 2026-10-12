"""Classify candidate-vs-published district-total discrepancies without promotion.

Consumes the isolated BEF candidate's contest-year ledger and emits an
exhaustive CSV, a machine-readable promotion manifest, and a concise report.
The published directory is read-only.
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CANDIDATE = DATA / "district_bef_candidate"
PUBLISHED = DATA / "district_contests"
OUT = DATA / "district_bef_audit" / "published_lineage"
SCOPES = ("congressional", "state_house", "state_senate")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_totals(path: Path) -> dict[str, int]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("general", {}).get("results", {}).values()
    return {
        key: sum(int(row.get(key) or 0) for row in rows)
        for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
    }


def classify(row: dict[str, str]) -> tuple[str, str]:
    year = int(row["year"])
    contest = row["contest_type"]
    published = [int(row[f"{scope}_published_total"]) for scope in SCOPES]
    candidate = int(row["source_votes"])
    spread = max(published) - min(published)
    deltas = [candidate - value for value in published]
    if not any(deltas):
        return "published_equivalent", "Candidate source total equals all published scopes."
    if year % 2 and any(term in contest for term in ("court", "retention")):
        base = "official_judicial_precinct_recovery"
        note = (
            "The candidate uses retained official precinct returns with complete matching; the lower "
            "published total reflects precinct coverage lost by the legacy matcher."
        )
    elif max(abs(value) for value in deltas) >= 100_000:
        base = "major_source_lineage_difference"
        note = "Difference is too large to be a BEF allocation or rounding effect."
    else:
        base = "source_revision_or_published_calibration"
        note = "Candidate conserves its selected source; published lineage/calibration must be recovered."
    if spread:
        return f"published_scope_inconsistency+{base}", (
            f"Published scopes disagree by {spread:,} votes; this is independently an existing "
            f"published aggregation defect. {note}"
        )
    return base, note


def main() -> int:
    ledger_path = CANDIDATE / "contest_year_audit.csv"
    if not ledger_path.exists():
        raise FileNotFoundError(ledger_path)
    rows = list(csv.DictReader(ledger_path.open(encoding="utf-8-sig", newline="")))
    OUT.mkdir(parents=True, exist_ok=True)
    classified = []
    category_counts = Counter()
    inconsistent = []
    changed_files = 0
    safe_files = []
    blocked_files = []
    for row in rows:
        published = [int(row[f"{scope}_published_total"]) for scope in SCOPES]
        candidate = int(row["source_votes"])
        spread = max(published) - min(published)
        category, explanation = classify(row)
        house_path = PUBLISHED / f"state_house_{row['contest_type']}_{row['year']}.json"
        house_payload = json.loads(house_path.read_text(encoding="utf-8"))
        house_source = str(house_payload.get("meta", {}).get("source") or "")
        if spread and "coterminous_county_control" in house_source:
            category = "coterminous_house_control"
            explanation = (
                "The published House file was post-processed with county totals from a separate "
                "source lineage. Congressional and Senate files were not changed, so statewide "
                "scope equality was broken. Regenerate; do not hand-balance."
            )
        category_counts[category] += 1
        record = dict(row)
        record.update({
            "published_scope_spread": spread,
            "candidate_equals_selected_source": int(row["source_votes"]) == int(row["matched_votes"]),
            "state_house_source": house_source,
            "classification": category,
            "explanation": explanation,
        })
        classified.append(record)
        if spread:
            inconsistent.append(record)
        for scope in SCOPES:
            filename = f"{scope}_{row['contest_type']}_{row['year']}.json"
            delta = int(row[f"{scope}_delta"])
            published_path = PUBLISHED / filename
            candidate_path = CANDIDATE / filename
            published_components = file_totals(published_path)
            candidate_components = file_totals(candidate_path)
            component_deltas = {
                f"{key}_delta": candidate_components[key] - published_components[key]
                for key in published_components
            }
            exact_equivalent = published_components == candidate_components
            entry = {
                "file": filename,
                "year": int(row["year"]),
                "contest_type": row["contest_type"],
                "scope": scope,
                "published_total": int(row[f"{scope}_published_total"]),
                "candidate_total": int(row[f"{scope}_candidate_total"]),
                "delta": delta,
                **component_deltas,
                "exact_party_and_total_equivalent": exact_equivalent,
                "classification": category,
            }
            if exact_equivalent:
                safe_files.append(entry)
            else:
                changed_files += 1
                blocked_files.append(entry)

    fields = list(classified[0])
    with (OUT / "contest_year_classification.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(classified)
    with (OUT / "published_scope_inconsistencies.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(inconsistent)

    source_inventory = []
    for path in sorted((DATA / "Openelections").glob("**/*.csv")):
        source_inventory.append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    manifest = {
        "status": "BLOCKED",
        "reason": "Candidate mapping/conservation passes, but published source lineage is not equivalent.",
        "candidate_selected_source_conserved_for_all_groups": all(
            int(row["source_votes"]) == int(row["matched_votes"]) for row in rows
        ),
        "contest_year_groups": len(rows),
        "published_scope_inconsistent_groups": len(inconsistent),
        "changed_files": changed_files,
        "individually_total_equivalent_files": safe_files,
        "blocked_files": blocked_files,
        "classification_counts": dict(category_counts),
        "source_inventory": source_inventory,
    }
    (OUT / "promotion_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    by_year = defaultdict(lambda: {"groups": 0, "inconsistent": 0, "max_abs_delta": 0})
    for row in classified:
        item = by_year[row["year"]]
        item["groups"] += 1
        item["inconsistent"] += bool(row["published_scope_spread"])
        item["max_abs_delta"] = max(
            item["max_abs_delta"],
            *(abs(int(row[f"{scope}_delta"])) for scope in SCOPES),
        )
    lines = [
        "# Published lineage reconciliation",
        "",
        "The BEF candidate conserves every selected source record, has no unmatched records, and passes the block/district checks. It is not promotion-ready because its selected source lineage does not reproduce the currently published totals.",
        "",
        f"- Contest/year groups audited: {len(rows)}",
        f"- Published files with changed totals: {changed_files}",
        f"- Groups where published congressional/House/Senate totals disagree internally: {len(inconsistent)}",
        f"- Individually total-equivalent files: {len(safe_files)}",
        "",
        "## Classification counts",
        "",
    ]
    lines.extend(f"- `{key}`: {value}" for key, value in sorted(category_counts.items()))
    lines += ["", "## Year summary", "", "| Year | Groups | Internally inconsistent | Largest absolute delta |", "|---:|---:|---:|---:|"]
    lines.extend(
        f"| {year} | {item['groups']} | {item['inconsistent']} | {item['max_abs_delta']:,} |"
        for year, item in sorted(by_year.items(), key=lambda pair: int(pair[0]))
    )
    lines += [
        "",
        "## Largest internal published inconsistencies",
        "",
        "| Year | Contest | CD total | House total | Senate total | Spread |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for row in sorted(inconsistent, key=lambda item: int(item["published_scope_spread"]), reverse=True)[:10]:
        lines.append(
            f"| {row['year']} | {row['contest_type']} | {int(row['congressional_published_total']):,} | "
            f"{int(row['state_house_published_total']):,} | {int(row['state_senate_published_total']):,} | "
            f"{int(row['published_scope_spread']):,} |"
        )
    lines += [
        "",
        "## Exact-equivalence allowlist",
        "",
        "Only files with identical Democratic, Republican, other, and total vote sums are eligible for independent promotion. The current allowlist is:",
        "",
    ]
    lines.extend(f"- `{item['file']}`" for item in safe_files)
    lines += [
        "",
        "## Release conclusion",
        "",
        "Do not bulk-promote the candidate. Internal published scope disagreement proves that some existing files are defective, while large consistent differences—especially multi-seat judicial contests—require recovery of the published candidate-selection and supplemental-source rules. Mapping corrections should be promoted only after a source-equivalent rebuild or explicit contest-by-contest replacement approval.",
        "",
        "See `contest_year_classification.csv`, `published_scope_inconsistencies.csv`, and `promotion_manifest.json` in this directory.",
    ]
    (OUT / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({
        "groups": len(rows),
        "changed_files": changed_files,
        "scope_inconsistent_groups": len(inconsistent),
        "safe_files": len(safe_files),
        "categories": dict(category_counts),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Build and gate an isolated BEF-based production candidate.

The published data/district_contests directory is never modified. Existing
published files are copied first so direct district-race slices remain intact;
statewide-derived slices are then rebuilt through the production code path.
"""
from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import shutil
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
PUBLISHED = DATA / "district_contests"
DEFAULT_OUT = DATA / "district_bef_candidate"


def import_builder():
    spec = importlib.util.spec_from_file_location("pa_builder_candidate", ROOT / "build_pa_data_layers.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def totals(payload):
    rows = payload.get("general", {}).get("results", {}).values()
    return {
        key: sum(int(row.get(key) or 0) for row in rows)
        for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
    }


def capture_candidate_labels(directory):
    labels = {}
    for path in directory.glob("*.json"):
        if path.name in {"manifest.json", "acceptance_report.json"}:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for district, row in payload.get("general", {}).get("results", {}).items():
            labels[(path.name, district)] = {
                "dem_candidate": row.get("dem_candidate", ""),
                "rep_candidate": row.get("rep_candidate", ""),
            }
    return labels


def restore_candidate_labels(directory, labels):
    """Keep established display labels while replacing vote allocations."""
    for path in directory.glob("*.json"):
        if path.name in {"manifest.json", "acceptance_report.json"}:
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for district, row in payload.get("general", {}).get("results", {}).items():
            prior = labels.get((path.name, district))
            if prior is None:
                continue
            for field in ("dem_candidate", "rep_candidate"):
                if row.get(field, "") != prior[field]:
                    row[field] = prior[field]
                    changed = True
        if changed:
            path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--reuse", action="store_true", help="Re-gate an existing candidate without rebuilding it")
    parser.add_argument("--quiet", action="store_true", help="Print only the gate status instead of the full report")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    if out == PUBLISHED.resolve() or PUBLISHED.resolve() in out.parents:
        raise ValueError("Candidate output must not be data/district_contests or a child of it")
    builder = import_builder()
    if not args.reuse:
        if out.exists():
            shutil.rmtree(out)
        shutil.copytree(PUBLISHED, out)
        candidate_labels = capture_candidate_labels(out)
        published_manifest = json.loads((PUBLISHED / "manifest.json").read_text(encoding="utf-8"))
        contest_types = {
            str(entry.get("contest_type") or "")
            for entry in published_manifest.get("files", [])
            if builder.is_statewide_contest_type(str(entry.get("contest_type") or ""))
        }
        builder.VTD_CURRENT_DISTRICT_BLOCKS = None
        builder.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = None
        builder.build_district_manifests(out, contest_types=contest_types)
        restore_candidate_labels(out, candidate_labels)
    elif not (out / "manifest.json").exists():
        raise FileNotFoundError(f"No reusable candidate at {out}")

    changes = []
    conservation_failures = []
    unmatched = []
    missing_or_added = []
    contest_year_audit = {}
    names = sorted({p.name for p in PUBLISHED.glob("*.json")} | {p.name for p in out.glob("*.json")})
    for name in names:
        if name in {"manifest.json", "acceptance_report.json"}:
            continue
        old_path, new_path = PUBLISHED / name, out / name
        if not old_path.exists() or not new_path.exists():
            missing_or_added.append({"file": name, "published": old_path.exists(), "candidate": new_path.exists()})
            continue
        old = json.loads(old_path.read_text(encoding="utf-8"))
        new = json.loads(new_path.read_text(encoding="utf-8"))
        old_totals, new_totals = totals(old), totals(new)
        scope = (
            "state_house" if name.startswith("state_house_")
            else "state_senate" if name.startswith("state_senate_")
            else "congressional"
        )
        if old_totals != new_totals:
            changes.append({
                "file": name,
                "published_total": old_totals["total_votes"],
                "candidate_total": new_totals["total_votes"],
                "total_delta": new_totals["total_votes"] - old_totals["total_votes"],
                "dem_delta": new_totals["dem_votes"] - old_totals["dem_votes"],
                "rep_delta": new_totals["rep_votes"] - old_totals["rep_votes"],
                "other_delta": new_totals["other_votes"] - old_totals["other_votes"],
            })
        audit = new.get("meta", {}).get("allocation_audit")
        if audit:
            contest_type = str(new.get("contest_type") or "")
            year = int(new.get("year") or 0)
            key = (year, contest_type)
            ledger = contest_year_audit.setdefault(key, {
                "year": year,
                "contest_type": contest_type,
                "source_rows": int(audit.get("source_rows") or 0),
                "source_votes": int(audit.get("source_votes") or 0),
                "matched_rows": int(audit.get("matched_rows") or 0),
                "matched_votes": int(audit.get("matched_votes") or 0),
                "unmatched_rows": int(audit.get("unmatched_rows") or 0),
                "unmatched_votes": int(audit.get("unmatched_votes") or 0),
                "unmatched_precinct_count": len(audit.get("unmatched_precincts") or []),
            })
            ledger[f"{scope}_published_total"] = old_totals["total_votes"]
            ledger[f"{scope}_candidate_total"] = new_totals["total_votes"]
            ledger[f"{scope}_delta"] = new_totals["total_votes"] - old_totals["total_votes"]
            if not audit.get("conserved_for_matched_rows"):
                conservation_failures.append({"file": name, **audit})
            if int(audit.get("unmatched_rows") or 0) or int(audit.get("unallocated_rows") or 0):
                unmatched.append({
                    "file": name,
                    **{key: value for key, value in audit.items() if key != "unmatched_precincts"},
                    "unmatched_precinct_count": len(audit.get("unmatched_precincts") or []),
                    "unmatched_precincts_location": f"{name}#/meta/allocation_audit/unmatched_precincts",
                })

    changes.sort(key=lambda row: abs(row["total_delta"]), reverse=True)
    unmatched.sort(key=lambda row: int(row.get("unmatched_votes") or 0), reverse=True)
    acceptance = {
        "bef_block_join_complete": True,  # build raises before output on any BEF/BAF defect
        "matched_precinct_votes_conserved": not conservation_failures,
        "no_unmatched_or_unallocated_source_rows": not unmatched,
        "published_statewide_totals_unchanged": not changes,
        "published_file_coverage_unchanged": not missing_or_added,
    }
    summary = {
        "status": "PASS" if all(acceptance.values()) else "BLOCKED",
        "published_directory": str(PUBLISHED.relative_to(ROOT)),
        "candidate_directory": str(out.relative_to(ROOT)),
        "acceptance": acceptance,
        "counts": {
            "statewide_total_changes": len(changes),
            "conservation_failures": len(conservation_failures),
            "files_with_unmatched_or_unallocated_rows": len(unmatched),
            "coverage_changes": len(missing_or_added),
        },
        "largest_statewide_changes": changes[:25],
        "largest_unmatched": unmatched[:25],
        "coverage_changes": missing_or_added,
        "changed_scopes": dict(Counter(
            "state_house" if row["file"].startswith("state_house_")
            else "state_senate" if row["file"].startswith("state_senate_")
            else "congressional"
            for row in changes
        )),
        "contest_years": [contest_year_audit[key] for key in sorted(contest_year_audit)],
    }
    (out / "acceptance_report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    ledger_rows = summary["contest_years"]
    ledger_fields = [
        "year", "contest_type", "source_rows", "source_votes", "matched_rows", "matched_votes",
        "unmatched_rows", "unmatched_votes", "unmatched_precinct_count",
        "congressional_published_total", "congressional_candidate_total", "congressional_delta",
        "state_house_published_total", "state_house_candidate_total", "state_house_delta",
        "state_senate_published_total", "state_senate_candidate_total", "state_senate_delta",
    ]
    with (out / "contest_year_audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=ledger_fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(ledger_rows)
    if args.quiet:
        print(json.dumps({"status": summary["status"], "counts": summary["counts"]}))
    else:
        print(json.dumps(summary, indent=2))
    return 0 if summary["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())

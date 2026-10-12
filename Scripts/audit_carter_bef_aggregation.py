"""Audit Carter-adjusted PA block/VTD assignments against 2022-line BEFs.

All generated files are confined to data/district_bef_audit.  The script does
not modify data/district_contests or any other published artifact.
"""
from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = DATA / "district_bef_audit"
VTD_CSV = DATA / "crosswalks" / "pa_block20_to_vtd20.csv"
BAF_ZIP = DATA / "BlockAssign_ST42_PA.zip"

SCOPES = {
    "congressional": {
        "bef": DATA / "42_PA_CD118.txt",
        "field": "CDFP",
        "old": DATA / "crosswalks" / "pa_block20_to_congressional_2022.csv",
        "max": 17,
    },
    "state_house": {
        "bef": DATA / "42_PA_SLDL22.txt",
        "field": "SLDLST",
        "old": DATA / "crosswalks" / "pa_block20_to_state_house_2022.csv",
        "max": 203,
    },
    "state_senate": {
        "bef": DATA / "42_PA_SLDU22.txt",
        "field": "SLDUST",
        "old": DATA / "crosswalks" / "pa_block20_to_state_senate_2022.csv",
        "max": 50,
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8",
        errors="replace", capture_output=True, check=False,
    )
    return result.stdout.strip()


def clean_id(value: object, width: int | None = None) -> str:
    text = str(value or "").strip()
    return text.zfill(width) if width and text.isdigit() else text


def load_carter_csv():
    rows, duplicates, invalid, county_mismatches = {}, [], [], []
    with VTD_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), 2):
            block = clean_id(row.get("block"), 15)
            county = clean_id(row.get("countyfp_dst"), 3)
            vtd = clean_id(row.get("dst_vtd"), 6)
            if len(block) != 15 or not block.isdigit() or not vtd:
                invalid.append({"row": row_number, "block": block, "county": county, "vtd": vtd})
                continue
            if block in rows:
                duplicates.append(block)
            rows[block] = (county, vtd)
            if block[2:5] != county:
                county_mismatches.append({"block": block, "geoid_county": block[2:5], "assigned_county": county})
    return rows, duplicates, invalid, county_mismatches


def load_zip_vtd():
    rows, duplicates = {}, []
    with zipfile.ZipFile(BAF_ZIP) as archive:
        info = archive.getinfo("BlockAssign_ST42_PA_VTD.txt")
        with archive.open(info) as raw:
            next(raw, None)
            for line in raw:
                parts = line.decode("utf-8", errors="replace").rstrip("\r\n").split("|")
                if len(parts) < 3:
                    continue
                block, county, vtd = clean_id(parts[0], 15), clean_id(parts[1], 3), clean_id(parts[2], 6)
                if block in rows:
                    duplicates.append(block)
                rows[block] = (county, vtd)
    return rows, duplicates, info


def load_assignment(path: Path, district_field: str | None = None):
    rows, duplicates, invalid = {}, [], []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, skipinitialspace=True)
        for row_number, row in enumerate(reader, 2):
            block = clean_id(row.get("GEOID") if district_field else row.get("block"), 15)
            district = clean_id(row.get(district_field) if district_field else row.get("district"))
            if block in rows:
                duplicates.append(block)
            rows[block] = district.lstrip("0") or "0"
            if len(block) != 15 or not block.isdigit() or not district.isdigit():
                invalid.append({"row": row_number, "block": block, "district": district})
    return rows, duplicates, invalid


def weights_from(carter, assignments):
    weights = defaultdict(lambda: defaultdict(int))
    for block, (county, vtd) in carter.items():
        district = assignments.get(block)
        if district:
            weights[(county, vtd)][district] += 1
    return weights


def split_summary(weights):
    splits = []
    for (county, vtd), districts in weights.items():
        if len(districts) > 1:
            splits.append({
                "county": county,
                "vtd": vtd,
                "districts": dict(sorted(districts.items(), key=lambda item: int(item[0]))),
                "blocks": sum(districts.values()),
            })
    return sorted(splits, key=lambda item: (-item["blocks"], item["county"], item["vtd"]))


def import_builder():
    spec = importlib.util.spec_from_file_location("pa_builder_audit", ROOT / "build_pa_data_layers.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def run_build(builder, target: Path, scope_weights, calibrated: bool):
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    builder.VTD_CURRENT_DISTRICT_BLOCKS = None
    builder.VTD_CURRENT_SCOPE_BLOCK_WEIGHTS = {
        scope: defaultdict(lambda: defaultdict(int), {
            key: defaultdict(int, counts) for key, counts in weights.items()
        }) for scope, weights in scope_weights.items()
    }
    original_calibration = builder.apply_dra_share_calibration
    if not calibrated:
        builder.apply_dra_share_calibration = lambda *_args, **_kwargs: None
    allocation_checks = {"calls": 0, "input_votes": 0, "output_votes": 0, "failures": []}
    original_allocate = builder.allocate_votes_by_block_counts

    def checked_allocate(votes, counts):
        result = original_allocate(votes, counts)
        allocation_checks["calls"] += 1
        allocation_checks["input_votes"] += int(votes or 0)
        allocation_checks["output_votes"] += sum(result.values())
        if counts and sum(result.values()) != int(votes or 0):
            allocation_checks["failures"].append({"votes": votes, "allocated": sum(result.values())})
        return result

    builder.allocate_votes_by_block_counts = checked_allocate
    try:
        builder.build_district_manifests(target)
    finally:
        builder.apply_dra_share_calibration = original_calibration
        builder.allocate_votes_by_block_counts = original_allocate
    return allocation_checks


def calibrate_existing_build(builder, source: Path, target: Path):
    """Apply the builder's optional DRA calibration without reparsing returns."""
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    nodes, sources = {}, {}
    payloads = {}
    for path in target.glob("*.json"):
        if path.name == "manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        key = (payload["scope"], payload["contest_type"], int(payload["year"]))
        nodes[key] = payload.get("general", {}).get("results", {})
        sources[key] = payload.get("meta", {}).get("source", "")
        payloads[key] = (path, payload)
    builder.apply_dra_share_calibration(nodes, sources)
    for key, (path, payload) in payloads.items():
        payload["general"]["results"] = nodes[key]
        payload["meta"]["source"] = sources.get(key, payload["meta"].get("source", ""))
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def json_totals(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    results = payload.get("general", {}).get("results", {})
    totals = {key: sum(int(row.get(key) or 0) for row in results.values()) for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")}
    return payload, results, totals


def compare_outputs(left_dir: Path, right_dir: Path, label: str):
    rows, coverage = [], []
    names = sorted({p.name for p in left_dir.glob("*.json")} | {p.name for p in right_dir.glob("*.json")})
    for name in names:
        if name == "manifest.json":
            continue
        left_path, right_path = left_dir / name, right_dir / name
        if not left_path.exists() or not right_path.exists():
            coverage.append({"file": name, "comparison": label, "left_exists": left_path.exists(), "right_exists": right_path.exists()})
            continue
        left, left_results, left_totals = json_totals(left_path)
        right, right_results, right_totals = json_totals(right_path)
        lmeta, rmeta = left.get("meta", {}), right.get("meta", {})
        if lmeta.get("districts_observed") != rmeta.get("districts_observed") or lmeta.get("coverage_percent") != rmeta.get("coverage_percent"):
            coverage.append({
                "file": name, "comparison": label,
                "left_observed": lmeta.get("districts_observed"), "right_observed": rmeta.get("districts_observed"),
                "left_coverage": lmeta.get("coverage_percent"), "right_coverage": rmeta.get("coverage_percent"),
            })
        for district in sorted(set(left_results) | set(right_results), key=lambda x: int(x) if x.isdigit() else x):
            lrow, rrow = left_results.get(district, {}), right_results.get(district, {})
            delta = int(rrow.get("total_votes") or 0) - int(lrow.get("total_votes") or 0)
            if delta or any(int(rrow.get(k) or 0) != int(lrow.get(k) or 0) for k in ("dem_votes", "rep_votes", "other_votes")):
                rows.append({
                    "comparison": label, "file": name, "district": district,
                    "left_total": int(lrow.get("total_votes") or 0), "right_total": int(rrow.get("total_votes") or 0),
                    "total_delta": delta,
                    "dem_delta": int(rrow.get("dem_votes") or 0) - int(lrow.get("dem_votes") or 0),
                    "rep_delta": int(rrow.get("rep_votes") or 0) - int(lrow.get("rep_votes") or 0),
                    "other_delta": int(rrow.get("other_votes") or 0) - int(lrow.get("other_votes") or 0),
                    "left_statewide_total": left_totals["total_votes"], "right_statewide_total": right_totals["total_votes"],
                    "statewide_delta": right_totals["total_votes"] - left_totals["total_votes"],
                })
    return rows, coverage


def write_csv(path: Path, rows):
    rows = list(rows)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fieldnames = []
    seen = set()
    for row in rows:
        for field in row:
            if field not in seen:
                seen.add(field)
                fieldnames.append(field)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    carter, carter_dupes, carter_invalid, carter_county_bad = load_carter_csv()
    zip_vtd, zip_dupes, zip_info = load_zip_vtd()
    common = set(carter) & set(zip_vtd)
    changed_vtd = [
        {"block": block, "zip_county": zip_vtd[block][0], "zip_vtd": zip_vtd[block][1], "carter_county": carter[block][0], "carter_vtd": carter[block][1]}
        for block in sorted(common) if zip_vtd[block] != carter[block]
    ]
    report = {
        "provenance": {
            "carter_bridge": str(VTD_CSV.relative_to(ROOT)),
            "carter_bridge_sha256": sha256(VTD_CSV),
            "git_first_commit": git("log", "--diff-filter=A", "--format=%H|%aI|%s", "--", str(VTD_CSV.relative_to(ROOT))).splitlines()[-1],
            "baf_zip": str(BAF_ZIP.relative_to(ROOT)),
            "baf_zip_sha256": sha256(BAF_ZIP),
            "zip_vtd_member_timestamp": list(zip_info.date_time),
            "relationship": "identical" if not changed_vtd and set(carter) == set(zip_vtd) else "different",
        },
        "vtd_join": {
            "carter_blocks": len(carter), "zip_vtd_blocks": len(zip_vtd),
            "carter_duplicates": len(carter_dupes), "zip_duplicates": len(zip_dupes),
            "carter_invalid": len(carter_invalid), "carter_county_mismatches": len(carter_county_bad),
            "carter_missing_from_zip": len(set(carter) - set(zip_vtd)),
            "zip_missing_from_carter": len(set(zip_vtd) - set(carter)),
            "changed_common_assignments": len(changed_vtd),
        },
        "scopes": {},
    }
    write_csv(OUT / "carter_vs_zip_vtd_changes.csv", changed_vtd)

    bef_weights, old_weights = {}, {}
    for scope, config in SCOPES.items():
        bef, bef_dupes, bef_invalid = load_assignment(config["bef"], config["field"])
        old, old_dupes, old_invalid = load_assignment(config["old"])
        bef_weights[scope], old_weights[scope] = weights_from(carter, bef), weights_from(carter, old)
        invalid_districts = sorted({value for value in bef.values() if not value.isdigit() or not (1 <= int(value) <= config["max"])})
        county_mismatches = [block for block in bef if len(block) != 15 or block[2:5] != carter.get(block, (block[2:5], ""))[0]]
        changed = sum(1 for block in set(bef) & set(old) if bef[block] != old[block])
        splits = split_summary(bef_weights[scope])
        write_csv(OUT / f"{scope}_split_vtds.csv", splits)
        report["scopes"][scope] = {
            "bef_file": str(config["bef"].relative_to(ROOT)), "bef_sha256": sha256(config["bef"]),
            "bef_blocks": len(bef), "duplicates": len(bef_dupes), "invalid_rows": len(bef_invalid),
            "invalid_district_ids": invalid_districts, "county_mismatches": len(county_mismatches),
            "missing_carter_blocks": len(set(carter) - set(bef)), "extra_bef_blocks": len(set(bef) - set(carter)),
            "old_crosswalk_blocks": len(old), "old_duplicates": len(old_dupes), "old_invalid": len(old_invalid),
            "blocks_changed_from_old_crosswalk": changed,
            "vtds": len(bef_weights[scope]), "split_vtds": len(splits),
        }

    builder = import_builder()
    checks = {}
    old_dir = OUT / "old_uncalibrated"
    bef_dir = OUT / "bef_uncalibrated"
    # The uncalibrated builder writes contest JSONs but no manifest. Treat a
    # complete-looking output directory as reusable so an audit rerun does not
    # silently perform two expensive full statewide rebuilds.
    old_complete = any(old_dir.glob("congressional_*.json")) and any(old_dir.glob("state_senate_*.json"))
    bef_complete = any(bef_dir.glob("congressional_*.json")) and any(bef_dir.glob("state_senate_*.json"))
    if not old_complete:
        checks["old_uncalibrated"] = run_build(builder, old_dir, old_weights, False)
    else:
        checks["old_uncalibrated"] = {"reused_complete_output": True}
    if not bef_complete:
        checks["bef_uncalibrated"] = run_build(builder, bef_dir, bef_weights, False)
    else:
        checks["bef_uncalibrated"] = {"reused_complete_output": True}
    calibrated_dir = OUT / "bef_calibrated"
    calibrated_complete = (calibrated_dir / "manifest.json").exists()
    if not calibrated_complete:
        calibrate_existing_build(builder, bef_dir, calibrated_dir)
        checks["bef_calibrated"] = {"derived_from_uncalibrated_output": True}
    else:
        checks["bef_calibrated"] = {"reused_complete_output": True}
    comparisons = []
    coverage = []
    for left, right, label in (
        (OUT / "old_uncalibrated", OUT / "bef_uncalibrated", "mapping_effect_old_to_bef"),
        (OUT / "bef_uncalibrated", OUT / "bef_calibrated", "calibration_effect"),
        (DATA / "district_contests", OUT / "bef_calibrated", "published_to_bef_calibrated"),
    ):
        rows, cov = compare_outputs(left, right, label)
        comparisons.extend(rows)
        coverage.extend(cov)
    comparisons.sort(key=lambda row: abs(row["total_delta"]), reverse=True)
    write_csv(OUT / "district_vote_changes.csv", comparisons)
    write_csv(OUT / "coverage_changes.csv", coverage)
    report["vote_conservation"] = checks
    report["comparisons"] = {
        "changed_district_rows": dict(Counter(row["comparison"] for row in comparisons)),
        "coverage_changes": len(coverage),
        "largest_changes": comparisons[:25],
    }
    (OUT / "audit_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    sys.exit(main())

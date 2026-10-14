#!/usr/bin/env python3
"""Add RDH-only Philadelphia mail residuals to VAP-controlled 2024 files."""

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DISTRICTS = DATA / "district_contests"

COLUMN_BUCKETS = {
    "G24PREDHAR": "dem_votes",
    "G24PRERTRU": "rep_votes",
    "G24PREGSTE": "other_votes",
    "G24PRELOLI": "other_votes",
    "G24USSDCAS": "dem_votes",
    "G24USSRMCC": "rep_votes",
    "G24USSCSEL": "other_votes",
    "G24USSGHAZ": "other_votes",
    "G24USSLTHO": "other_votes",
    "G24USSOWRI": "other_votes",
}


def allocate_exact(votes, weights):
    total = sum(float(value) for value in weights.values())
    raw = {district: float(value) * votes / total for district, value in weights.items()}
    allocated = {district: int(value) for district, value in raw.items()}
    remainder = int(votes) - sum(allocated.values())
    order = sorted(raw, key=lambda district: (raw[district] - allocated[district], district), reverse=True)
    for district in order[:remainder]:
        allocated[district] += 1
    return allocated


def finalize(row):
    dem = int(row.get("dem_votes") or 0)
    rep = int(row.get("rep_votes") or 0)
    other = int(row.get("other_votes") or 0)
    total = dem + rep + other
    margin = dem - rep
    row.update({
        "total_votes": total,
        "winner": "D" if margin > 0 else "R" if margin < 0 else "T",
        "margin": float(abs(margin)),
        "margin_pct": abs(margin) / total * 100 if total else 0.0,
    })


def main():
    audit_path = DATA / "rdh_2024_district_vote_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    residuals = audit.get("residual_allocations") or []
    for scope in ("congressional", "state_house", "state_senate"):
        for contest in ("president",):
            path = DISTRICTS / f"{scope}_{contest}_2024.json"
            document = json.loads(path.read_text(encoding="utf-8"))
            results = document["general"]["results"]
            touched = defaultdict(lambda: defaultdict(int))
            if scope == "congressional":
                # Each source row appears in both legislative-scope audit lists;
                # use one copy and retain its explicit congressional district.
                selected = [
                    row for row in residuals
                    if row.get("scope") == "state_house" and row.get("contest") == contest
                ]
                for row in selected:
                    district = str(row["congressional_district"]).lstrip("0") or "0"
                    bucket = COLUMN_BUCKETS[row["column"]]
                    votes = int(row["votes"])
                    results[district][bucket] = int(results[district].get(bucket) or 0) + votes
                    touched[bucket][district] += votes
            else:
                selected = [
                    row for row in residuals
                    if row.get("scope") == scope and row.get("contest") == contest
                ]
                for row in selected:
                    bucket = COLUMN_BUCKETS[row["column"]]
                    allocated = allocate_exact(int(row["votes"]), row["district_weights"])
                    for district, votes in allocated.items():
                        results[str(district)][bucket] = int(results[str(district)].get(bucket) or 0) + votes
                        touched[bucket][str(district)] += votes
            controls = audit["controls"][contest]
            for bucket in ("dem_votes", "rep_votes", "other_votes"):
                observed = sum(int(result.get(bucket) or 0) for result in results.values())
                delta = int(controls[bucket]) - observed
                if delta > 0:
                    for district, votes in allocate_exact(delta, touched[bucket]).items():
                        results[district][bucket] = int(results[district].get(bucket) or 0) + votes
                elif delta < 0:
                    for district, votes in allocate_exact(-delta, touched[bucket]).items():
                        results[district][bucket] = int(results[district].get(bucket) or 0) - votes
            for result in results.values():
                finalize(result)
            marker = "rdh_2024_residual_votes"
            source = str(document.setdefault("meta", {}).get("source") or "")
            if marker not in source:
                document["meta"]["source"] = f"{source}+{marker}" if source else marker
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            print(f"supplemented {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

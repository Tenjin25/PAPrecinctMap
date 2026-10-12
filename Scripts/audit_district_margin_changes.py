#!/usr/bin/env python3
import csv
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD_ZIP = ROOT / "data" / "district_bef_audit" / "prepromotion_district_contests.zip"
NEW_DIR = ROOT / "data" / "district_contests"
OUT_CSV = ROOT / "data" / "district_bef_audit" / "published_margin_changes.csv"
OUT_JSON = ROOT / "data" / "district_bef_audit" / "published_margin_summary.json"


def winner(margin):
    return "D" if margin > 0 else "R" if margin < 0 else "T"


def main():
    rows = []
    with zipfile.ZipFile(OLD_ZIP) as archive:
        names = set(archive.namelist())
        for new_path in sorted(NEW_DIR.glob("*.json")):
            if new_path.name == "manifest.json":
                continue
            member = f"data/district_contests/{new_path.name}"
            if member not in names:
                continue
            old = json.loads(archive.read(member))
            new = json.loads(new_path.read_text(encoding="utf-8"))
            old_results = old.get("general", {}).get("results", {})
            new_results = new.get("general", {}).get("results", {})
            for district in sorted(set(old_results) & set(new_results), key=lambda x: (len(x), x)):
                before = old_results[district]
                after = new_results[district]
                old_margin = int(before.get("dem_votes", 0)) - int(before.get("rep_votes", 0))
                new_margin = int(after.get("dem_votes", 0)) - int(after.get("rep_votes", 0))
                old_total = int(before.get("total_votes", 0))
                new_total = int(after.get("total_votes", 0))
                old_pct = 100 * old_margin / old_total if old_total else 0.0
                new_pct = 100 * new_margin / new_total if new_total else 0.0
                rows.append({
                    "file": new_path.name,
                    "scope": new.get("scope", ""),
                    "contest_type": new.get("contest_type", ""),
                    "year": new.get("year", ""),
                    "district": district,
                    "old_margin": old_margin,
                    "new_margin": new_margin,
                    "margin_delta": new_margin - old_margin,
                    "old_margin_pct": round(old_pct, 6),
                    "new_margin_pct": round(new_pct, 6),
                    "margin_pp_delta": round(new_pct - old_pct, 6),
                    "old_winner": winner(old_margin),
                    "new_winner": winner(new_margin),
                    "winner_changed": winner(old_margin) != winner(new_margin),
                })

    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    changed = [r for r in rows if r["margin_delta"] or r["margin_pp_delta"]]
    flips = [r for r in rows if r["winner_changed"]]
    summary = {
        "district_rows_compared": len(rows),
        "district_rows_with_margin_change": len(changed),
        "winner_flips": len(flips),
        "democratic_margin_increased": sum(r["margin_pp_delta"] > 0 for r in changed),
        "republican_margin_increased": sum(r["margin_pp_delta"] < 0 for r in changed),
        "largest_percentage_point_changes": sorted(changed, key=lambda r: abs(r["margin_pp_delta"]), reverse=True)[:25],
        "largest_raw_vote_margin_changes": sorted(changed, key=lambda r: abs(r["margin_delta"]), reverse=True)[:25],
        "winner_changes": sorted(flips, key=lambda r: abs(r["margin_pp_delta"]), reverse=True),
    }
    OUT_JSON.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

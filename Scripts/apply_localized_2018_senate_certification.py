"""Apply certified 2018 Senate county deltas without statewide residual raking."""
from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
DELTA_FILE = DATA / "benchmarks" / "pa_county_2018_us_senate_district_deltas.csv"
BASE_TOTALS = {"dem": 2_792_615, "rep": 2_135_149, "other": 82_126}
FINAL_TOTALS = {"dem": 2_792_437, "rep": 2_134_848, "other": 82_115}


def totals(results):
    return {bucket: sum(int(row[f"{bucket}_votes"]) for row in results.values()) for bucket in BASE_TOTALS}


def main() -> int:
    with DELTA_FILE.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    grouped = defaultdict(list)
    checks = defaultdict(int)
    for row in rows:
        grouped[row["scope"]].append(row)
        checks[(row["scope"], row["countyfp"], row["bucket"])] += int(row["district_delta"])
    for (scope, county, bucket), allocated in checks.items():
        stated = int(next(row["delta"] for row in rows if row["scope"] == scope and row["countyfp"] == county and row["bucket"] == bucket))
        if allocated != stated:
            raise RuntimeError(f"{scope} county {county} {bucket}: allocated {allocated}, expected {stated}")

    for scope, changes in grouped.items():
        path = DATA / "district_contests" / f"{scope}_us_senate_2018.json"
        document = json.loads(path.read_text(encoding="utf-8"))
        results = document["general"]["results"]
        before = totals(results)
        already_controlled = before == FINAL_TOTALS
        if not already_controlled and before != BASE_TOTALS:
            raise RuntimeError(f"{scope}: unexpected baseline {before}")
        if not already_controlled:
            for row in changes:
                result = results[row["district"]]
                field = f"{row['bucket']}_votes"
                result[field] = int(result[field]) + int(row["district_delta"])
            for result in results.values():
                dem, rep, other = (int(result[f"{bucket}_votes"]) for bucket in ("dem", "rep", "other"))
                total, margin = dem + rep + other, dem - rep
                result.update({
                    "total_votes": total,
                    "winner": "D" if margin > 0 else "R" if margin < 0 else "T",
                    "margin": float(abs(margin)),
                    "margin_pct": abs(margin) / total * 100 if total else 0.0,
                })
        after = totals(results)
        if after != FINAL_TOTALS:
            raise RuntimeError(f"{scope}: controlled totals {after} != {FINAL_TOTALS}")
        meta = document.setdefault("meta", {})
        marker = "+localized_county_vote_control/benchmarks/pa_county_2018_us_senate_certified.csv"
        if marker not in meta.get("source", ""):
            meta["source"] = meta.get("source", "") + marker
        meta["localized_county_vote_control"] = {
            "countyfp": "129", "county": "Westmoreland", "write_ins_excluded": 1568,
            "source_named_total": sum(BASE_TOTALS.values()), "control_named_total": sum(FINAL_TOTALS.values()),
            "allocation": DELTA_FILE.relative_to(DATA).as_posix(),
        }
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{scope}: {'already controlled at' if already_controlled else str(before) + ' ->'} {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
import csv
import sys
from pathlib import Path


def totals(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("general", {}).get("results", {}).values()
    return {
        key: sum(int(row.get(key) or 0) for row in rows)
        for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
    }


def main():
    contest_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/district_contests")
    selected_year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    failures = []
    presidential_totals = {}
    statewide = {}
    for source in Path("data/Openelections").glob("*/*__pa__general__precinct.csv"):
        try:
            year = int(source.parent.name)
        except ValueError:
            continue
        with source.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                office = (row.get("office") or "").strip().lower()
                if office != "president":
                    continue
                statewide[year] = statewide.get(year, 0.0) + float(row.get("votes") or 0)
    for path in sorted(contest_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if selected_year is not None and payload.get("year") != selected_year:
            continue
        result = totals(path)
        component_total = result["dem_votes"] + result["rep_votes"] + result["other_votes"]
        if component_total != result["total_votes"]:
            failures.append(f"{path.name}: components={component_total}, total={result['total_votes']}")
        if payload.get("contest_type") == "president" and payload.get("year") in statewide:
            source_total = round(statewide[payload["year"]])
            if result["total_votes"] > source_total:
                failures.append(
                    f"{path.name}: district total {result['total_votes']} exceeds source total {source_total}"
                )
            presidential_totals.setdefault(payload["year"], {})[payload.get("scope") or path.name] = result["total_votes"]
    for year, scope_totals in sorted(presidential_totals.items()):
        # Each scope rounds fractional allocations independently, so a small
        # difference (at most roughly one vote per district) is expected.
        if max(scope_totals.values()) - min(scope_totals.values()) > 250:
            failures.append(
                f"{year} presidential totals differ by scope: "
                + ", ".join(f"{scope}={total}" for scope, total in sorted(scope_totals.items()))
            )
    if failures:
        print("\n".join(failures))
        return 1
    label = f" for {selected_year}" if selected_year is not None else ""
    print(f"District vote-conservation checks passed{label}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

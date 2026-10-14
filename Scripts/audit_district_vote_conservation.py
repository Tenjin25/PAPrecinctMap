import json
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


OFFICE_CODES = {
    "president": "USP",
    "us_senate": "USS",
    "governor": "GOV",
    "attorney_general": "ATT",
    "auditor": "AUD",
    "treasurer": "TRE",
}


def totals(path: Path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("general", {}).get("results", {}).values()
    return {
        key: sum(int(row.get(key) or 0) for row in rows)
        for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
    }


def statewide_control(year: int, contest: str):
    benchmark = Path(f"data/benchmarks/pa_congressional_{year}_{contest}.csv")
    if benchmark.exists():
        with benchmark.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return {
            key: sum(int(float(row.get(key) or 0)) for row in rows)
            for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
        }
    path = Path(f"data/contests/{contest}_{year}.json")
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8")).get("rows", [])
    return {
        key: sum(int(row.get(key) or 0) for row in rows)
        for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")
    }


def external_source_control(year: int, contest: str):
    """Read a control independently of the published county/district JSONs."""
    for stem in ("vest", "rdh"):
        audit = Path(f"data/{stem}_{year}_district_vote_audit.json")
        if not audit.exists():
            continue
        payload = json.loads(audit.read_text(encoding="utf-8"))
        value = (payload.get("controls") or {}).get(contest)
        if isinstance(value, dict):
            return {key: int(value[key]) for key in ("dem_votes", "rep_votes", "other_votes", "total_votes")}, str(audit)
        if value is not None:
            return {"total_votes": int(value)}, str(audit)

    office_code = OFFICE_CODES.get(contest)
    source = Path(f"data/ElectionReturns_{year}_General_PrecinctReturns.txt")
    if not office_code or not source.exists():
        return {}, ""
    # Reuse the production raw-export parser, but compare its result directly
    # with the published files rather than with a derived county JSON.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import regenerate_pa_district_jsons_from_crosswalks as builder

    rows, _candidates = builder.parse_precinct_returns(source, year, office_code)
    control = {
        f"{bucket}_votes": round(sum(float(values.get(bucket) or 0) for values in rows.values()))
        for bucket in ("dem", "rep", "other")
    }
    control["total_votes"] = sum(control.values())
    return control, str(source)


def main():
    contest_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "data/district_contests")
    selected_year = int(sys.argv[2]) if len(sys.argv) > 2 else None
    failures = []
    external_controls = {}
    presidential_totals = {}
    statewide = defaultdict(lambda: Counter())
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
                party = (row.get("party") or "").strip().upper()
                bucket = "dem_votes" if party == "DEM" else "rep_votes" if party == "REP" else "other_votes"
                statewide[year][bucket] += float(row.get("votes") or 0)
                statewide[year]["total_votes"] += float(row.get("votes") or 0)
    for path in sorted(contest_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        if selected_year is not None and payload.get("year") != selected_year:
            continue
        result = totals(path)
        control_key = (int(payload.get("year") or 0), str(payload.get("contest_type") or ""))
        if control_key not in external_controls:
            external_controls[control_key] = external_source_control(*control_key)
        external_control, external_source = external_controls[control_key]
        for key, expected in external_control.items():
            if result[key] != expected:
                failures.append(
                    f"{path.name}: {key} {result[key]} != external control {expected} ({external_source})"
                )
        component_total = result["dem_votes"] + result["rep_votes"] + result["other_votes"]
        if component_total != result["total_votes"]:
            failures.append(f"{path.name}: components={component_total}, total={result['total_votes']}")
        source_label = str(payload.get("meta", {}).get("source") or "")
        allocation_audit = payload.get("meta", {}).get("allocation_audit") or {}
        if allocation_audit:
            audited_source_total = int(allocation_audit.get("source_votes") or 0)
            audited_delta = int(allocation_audit.get("allocation_vote_delta") or 0)
            audited_unallocated = int(allocation_audit.get("unallocated_votes") or 0)
            if allocation_audit.get("conserved_for_matched_rows"):
                if result["total_votes"] != audited_source_total:
                    failures.append(
                        f"{path.name}: total {result['total_votes']} != audited source {audited_source_total}"
                    )
                if audited_delta != 0 or audited_unallocated != 0:
                    failures.append(
                        f"{path.name}: conserved audit has delta={audited_delta}, "
                        f"unallocated={audited_unallocated}"
                    )
        if (
            payload.get("contest_type") == "president"
            and "statewide_vote_control/" in source_label
            and not external_control
        ):
            control = statewide_control(payload["year"], "president")
            for key, expected in control.items():
                if result[key] != expected:
                    failures.append(
                        f"{path.name}: controlled {key} {result[key]} != statewide {expected}"
                    )
        elif (
            payload.get("contest_type") == "president"
            and payload.get("year") in statewide
            and not external_control
        ):
            source_control = {
                key: round(value) for key, value in statewide[payload["year"]].items()
            }
            for key, expected in source_control.items():
                if result[key] != expected:
                    failures.append(
                        f"{path.name}: {key} {result[key]} != OpenElections source {expected}"
                    )
            presidential_totals.setdefault(payload["year"], {})[payload.get("scope") or path.name] = {
                "total": result["total_votes"],
                "source": source_label,
            }
    for year, scope_totals in sorted(presidential_totals.items()):
        # Each scope rounds fractional allocations independently, so a small
        # difference (at most roughly one vote per district) is expected.
        totals_only = [item["total"] for item in scope_totals.values()]
        has_exact_benchmark = any(
            "exact_district_benchmark/" in item["source"]
            for item in scope_totals.values()
        )
        if not has_exact_benchmark and max(totals_only) - min(totals_only) > 250:
            failures.append(
                f"{year} presidential totals differ by scope: "
                + ", ".join(
                    f"{scope}={item['total']}"
                    for scope, item in sorted(scope_totals.items())
                )
            )
    if failures:
        print("\n".join(failures))
        return 1
    label = f" for {selected_year}" if selected_year is not None else ""
    print(f"District vote-conservation checks passed{label}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

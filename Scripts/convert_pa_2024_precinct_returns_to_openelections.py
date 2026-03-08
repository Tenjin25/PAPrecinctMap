import csv
import json
from pathlib import Path


BASE = Path(__file__).resolve().parents[1]
SOURCE = BASE / "Data" / "erstat_2024_g_268768_20250129.txt"
COUNTIES = BASE / "Data" / "pa_counties.geojson"
OUTPUT = BASE / "Data" / "Openelections" / "2024" / "20241105__pa__general__precinct_official.csv"


OFFICE_MAP = {
    "USP": ("President", None),
    "USS": ("U.S. Senate", None),
    "GOV": ("Governor", None),
    "ATT": ("Attorney General", None),
    "AUD": ("Auditor General", None),
    "TRE": ("State Treasurer", None),
    "USC": ("U.S. House", 18),
    "STS": ("State Senate", 19),
    "STH": ("State House", 20),
}


def load_county_lookup(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    lookup = {}
    for feature in data.get("features", []):
        props = feature.get("properties", {}) or {}
        fips = str(props.get("COUNTYFP20") or props.get("COUNTYFP") or "").zfill(3)
        name = (props.get("NAME20") or props.get("NAME") or "").strip()
        if fips and name:
            lookup[fips] = name
    return lookup


def smart_title(value: str) -> str:
    parts = [part for part in (value or "").strip().split() if part]
    if not parts:
        return ""
    return " ".join(
        part if len(part) == 1 and part.isalpha() else part.title()
        for part in parts
    )


def build_candidate(row: list[str]) -> str:
    name_parts = []
    first = (row[12] or "").strip()
    middle = (row[13] or "").strip()
    last = (row[11] or "").strip()
    suffix = (row[14] or "").strip()
    for part in (first, middle, last, suffix):
        if part:
            name_parts.append(part)
    candidate = smart_title(" ".join(name_parts))
    return candidate or "Write Ins"


def build_precinct(row: list[str]) -> str:
    precinct = " ".join(part for part in row[22:27] if part).strip()
    return smart_title(precinct)


def main() -> None:
    county_lookup = load_county_lookup(COUNTIES)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    with SOURCE.open("r", encoding="utf-8-sig", errors="ignore", newline="") as src, OUTPUT.open(
        "w", encoding="utf-8", newline=""
    ) as dst:
        reader = csv.reader(src)
        writer = csv.DictWriter(
            dst,
            fieldnames=[
                "county",
                "precinct",
                "office",
                "district",
                "party",
                "candidate",
                "votes",
                "election_day",
                "mail",
                "provisional",
            ],
        )
        writer.writeheader()

        for row in reader:
            if not row or len(row) < 31:
                continue

            office_code = (row[8] or "").strip().upper()
            office_info = OFFICE_MAP.get(office_code)
            if not office_info:
                continue

            office_name, district_index = office_info
            county_fips = str(row[29] or "").strip().zfill(3)
            county_name = county_lookup.get(county_fips)
            precinct_name = build_precinct(row)
            votes = (row[15] or "").strip()

            if not county_name or not precinct_name or not votes:
                continue

            district = ""
            if district_index is not None and district_index < len(row):
                district = (row[district_index] or "").strip()

            writer.writerow(
                {
                    "county": county_name,
                    "precinct": precinct_name,
                    "office": office_name,
                    "district": district,
                    "party": (row[9] or "").strip(),
                    "candidate": build_candidate(row),
                    "votes": votes,
                    "election_day": "",
                    "mail": "",
                    "provisional": "",
                }
            )


if __name__ == "__main__":
    main()

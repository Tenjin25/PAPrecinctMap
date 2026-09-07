"""Audit browser-ready precinct returns against the current map geometry."""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def norm(value: object) -> str:
    return " ".join(str(value or "").upper().split())


def comparison_key(value: object) -> str:
    text = norm(value)
    for pattern, replacement in (
        (r"\bX\b", "DISTRICT"), (r"\bD\b", "DISTRICT"),
        (r"\bW\b", "WARD"), (r"\bP\b", "PRECINCT"),
        (r"\bTWP\b", "TOWNSHIP"), (r"\bBORO\b", "BOROUGH"),
    ):
        text = re.sub(pattern, replacement, text)
    return re.sub(r"[^A-Z0-9]", "", text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=20)
    args = parser.parse_args()

    geometry = json.loads((DATA / "pa_current_voting_districts.geojson").read_text(encoding="utf-8"))
    target_names = {
        norm((feature.get("properties") or {}).get("precinct_norm"))
        for feature in geometry.get("features") or []
    }
    target_names.discard("")
    target_labels_by_county: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for feature in geometry.get("features") or []:
        props = feature.get("properties") or {}
        county = norm(props.get("county_nam"))
        target = norm(props.get("precinct_norm"))
        label = norm(props.get("precinct_name") or props.get("NAME"))
        if county and target and label:
            target_labels_by_county[county].append((target, label))
    manifest = json.loads((DATA / "precinct_returns_manifest.json").read_text(encoding="utf-8"))

    for entry in manifest.get("years") or []:
        path = ROOT / entry["output"]
        observed = set()
        raw_spellings: dict[str, set[str]] = defaultdict(set)
        counties_by_key: dict[str, set[str]] = defaultdict(set)
        row_counts: dict[str, int] = defaultdict(int)
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                raw = str(row.get("precinct") or "").strip()
                key = norm(raw)
                if not key:
                    continue
                observed.add(key)
                raw_spellings[key].add(raw)
                counties_by_key[key].add(norm(row.get("county")))
                row_counts[key] += 1

        unmatched = sorted(observed - target_names, key=lambda key: (-row_counts[key], key))
        missing = target_names - observed
        uncapped = sorted(
            key for key, spellings in raw_spellings.items()
            if any(spelling != spelling.upper() for spelling in spellings)
        )
        print(
            f"{entry['year']}: {len(observed & target_names):,}/{len(target_names):,} targets hit; "
            f"{len(unmatched):,} unmatched source keys; {len(missing):,} empty targets; "
            f"{len(uncapped):,} non-uppercase source keys"
        )
        for key in unmatched[: max(0, args.top)]:
            spelling = sorted(raw_spellings[key])[0]
            county = sorted(counties_by_key[key])[0] if counties_by_key[key] else ""
            source_label = spelling.split(" - ", 1)[1] if " - " in spelling else spelling
            ranked = sorted(
                (
                    difflib.SequenceMatcher(None, comparison_key(source_label), comparison_key(label)).ratio(),
                    target,
                    label,
                )
                for target, label in target_labels_by_county.get(county, [])
            )
            suggestions = "; ".join(
                f"{target} {label} ({score:.2f})" for score, target, label in ranked[-3:][::-1]
            )
            print(f"  {row_counts[key]:>5} rows  {spelling} -> {suggestions or 'no county candidate'}")


if __name__ == "__main__":
    main()

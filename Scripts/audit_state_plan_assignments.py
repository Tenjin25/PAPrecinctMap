"""Compare retained Census BEFs with downloaded official 2022 state plans."""
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/district_reconciliation_work/state_plan_sources"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SCOPES = {"congressional": ("42_PA_CD118.txt", "CDFP"),
          "state_house": ("42_PA_SLDL22.txt", "SLDLST"),
          "state_senate": ("42_PA_SLDU22.txt", "SLDUST")}


def state_rows(path):
    if not zipfile.is_zipfile(path):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            yield from csv.reader(handle)
        return
    # The official Carter URL ends in .csv but serves an XLSX workbook.
    with zipfile.ZipFile(path) as archive:
        strings = ["".join(node.itertext()) for node in
                   ET.fromstring(archive.read("xl/sharedStrings.xml"))]
        with archive.open("xl/worksheets/sheet1.xml") as handle:
            for _, node in ET.iterparse(handle, events=("end",)):
                if node.tag != NS + "row":
                    continue
                values = []
                for cell in node:
                    value = cell.findtext(NS + "v", "")
                    values.append(strings[int(value)] if cell.get("t") == "s" else value)
                yield values
                node.clear()


def main():
    summary, differences, fragments = {}, [], []
    for scope, (filename, field) in SCOPES.items():
        path = OUT / f"{scope}.csv"
        state = {}
        duplicates = []
        for row in state_rows(path):
            if len(row) < 2 or not row[0].startswith("42"):
                continue
            block, district = row[0].strip(), row[1].strip().lstrip("0") or "0"
            if block in state:
                duplicates.append(block)
            state[block] = district
        with (ROOT / "data" / filename).open(encoding="utf-8-sig", newline="") as handle:
            census = {row["GEOID"]: row[field].strip().lstrip("0") or "0"
                      for row in csv.DictReader(handle, skipinitialspace=True)}
        changed = sorted(block for block in state.keys() & census.keys() if state[block] != census[block])
        extras = sorted(state.keys() - census.keys())
        missing = sorted(census.keys() - state.keys())
        parents = defaultdict(dict)
        for block in extras:
            parents[block[:15]][block] = state[block]
        for parent, children in sorted(parents.items()):
            fragments.append({"scope": scope, "parent_block": parent,
                              "census_district": census.get(parent),
                              "state_fragments": children,
                              "crosses_district_boundary": len(set(children.values())) > 1})
        for block in sorted(set(changed + extras + missing)):
            differences.append({"scope": scope, "block": block,
                                "state_district": state.get(block, ""),
                                "census_district": census.get(block, ""),
                                "kind": "assignment" if block in changed else "state_only" if block in state else "census_only"})
        summary[scope] = {"state_rows": len(state), "census_rows": len(census),
                          "state_duplicate_ids": duplicates,
                          "common_assignment_changes": len(changed),
                          "state_only": len(extras), "census_only": len(missing),
                          "state_nonstandard_ids": [block for block in state if len(block) != 15 or not block.isdigit()],
                          "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                          "district_counts": dict(Counter(state.values()))}
    with (OUT / "assignment_differences.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["scope", "block", "state_district", "census_district", "kind"])
        writer.writeheader()
        writer.writerows(differences)
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (OUT / "fragment_assignments.json").write_text(json.dumps(fragments, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({scope: {key: value for key, value in row.items()
                            if key not in {"district_counts", "state_nonstandard_ids", "state_duplicate_ids"}}
                      for scope, row in summary.items()}, indent=2))


if __name__ == "__main__":
    main()

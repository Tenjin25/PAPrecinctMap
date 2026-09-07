import json
import sys
from pathlib import Path


def main() -> int:
    year = int(sys.argv[1])
    contest_dir = Path("data/contests")
    district_dir = Path("data/district_contests")
    names = {}
    for path in contest_dir.glob(f"*_{year}.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("rows", [])
        if not rows:
            continue
        contest = payload.get("contest") or path.stem.rsplit("_", 1)[0]
        names[contest] = (
            rows[0].get("dem_candidate") or "",
            rows[0].get("rep_candidate") or "",
        )

    for path in district_dir.glob(f"*_{year}.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates = names.get(payload.get("contest_type"))
        if not candidates:
            continue
        for result in payload.get("general", {}).get("results", {}).values():
            result["dem_candidate"], result["rep_candidate"] = candidates
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

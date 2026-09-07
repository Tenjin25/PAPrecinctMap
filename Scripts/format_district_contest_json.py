import json
import sys
from pathlib import Path


def main() -> int:
    for raw_path in sys.argv[1:]:
        path = Path(raw_path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        results = payload.get("general", {}).get("results", {})
        payload["general"]["results"] = {
            key: results[key] for key in sorted(results, key=int)
        }
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

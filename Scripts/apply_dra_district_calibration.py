"""Apply reviewed DRA/RDH shares to an existing district JSON with exact controls."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import regenerate_pa_district_jsons_from_crosswalks as rebuild


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=rebuild.SCOPES, required=True)
    parser.add_argument("--contest", required=True)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--control-only", action="store_true")
    args = parser.parse_args()

    payload = json.loads(args.path.read_text(encoding="utf-8"))
    results = payload["general"]["results"]
    calibration = ""
    if not args.control_only:
        calibration = rebuild.apply_dra_district_shares(
            args.scope, args.contest, args.year, results
        )
        if not calibration:
            raise SystemExit("no reviewed DRA/RDH share file for requested layer")
    control = rebuild.apply_statewide_vote_control(args.contest, args.year, results)
    if not control:
        raise SystemExit("no statewide vote control for requested layer")
    additions = []
    if calibration:
        additions.append(f"dra_share_calibration/{calibration}")
    additions.append(f"statewide_vote_control/{control}")
    payload["meta"]["source"] = "+".join([
        payload["meta"].get("source", ""), *additions
    ]).lstrip("+")
    args.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

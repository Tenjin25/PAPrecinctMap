#!/usr/bin/env python3
"""Build a checksum ledger for district-aggregation source artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUTPUT = DATA / "source_ledger.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def entry(path: Path, role: str, **extra):
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "role": role,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        **extra,
    }


def main() -> int:
    sources = []
    vap = DATA / "crosswalks" / "pa_block20_vap.csv.gz"
    sources.append(entry(
        vap,
        "2020 Census block voting-age population (P0030001)",
        upstream_url="https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Pennsylvania/pa2020.pl.zip",
        upstream_sha256="2d33a7dab29c8dd5692bbde203d253e06eebbc44fcbaa96b1caa958d454026ae",
        acquired="2026-10-15",
    ))
    for path, role in (
        (DATA / "crosswalks" / "pa_block20_to_vtd20.csv", "Carter-adjusted block-to-VTD BAF"),
        (DATA / "42_PA_CD118.txt", "Carter congressional BEF"),
        (DATA / "42_PA_SLDL22.txt", "Carter State House BEF"),
        (DATA / "42_PA_SLDU22.txt", "Carter State Senate BEF"),
        (DATA / "crosswalks" / "pa_historical_precinct_to_vtd20.csv", "NHGIS historical precinct lineage"),
        (DATA / "crosswalks" / "pa_modern_precinct_to_vtd20.csv", "modern precinct lineage"),
    ):
        sources.append(entry(path, role))
    for path in sorted((DATA / "benchmarks").glob("pa_county_*_certified.csv")):
        sources.append(entry(path, "certified county party control"))
    payload = {
        "generated": "2026-10-15",
        "policy": {
            "whole_county_threshold": 0.999,
            "residual_scope": "county only",
            "rounding": "largest remainder within county/party",
            "dra_shares": "diagnostic only",
        },
        "sources": sources,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print({"sources": len(sources), "output": str(OUTPUT)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

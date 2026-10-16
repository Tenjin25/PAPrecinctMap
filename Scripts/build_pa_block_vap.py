#!/usr/bin/env python3
"""Derive the retained Pennsylvania 2020 Census block-VAP artifact."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "crosswalks" / "pa_block20_vap.csv.gz"
OFFICIAL_SHA256 = "2d33a7dab29c8dd5692bbde203d253e06eebbc44fcbaa96b1caa958d454026ae"
SOURCE_URL = "https://www2.census.gov/programs-surveys/decennial/2020/data/01-Redistricting_File--PL_94-171/Pennsylvania/pa2020.pl.zip"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_block_vap(path: Path) -> dict[str, int]:
    logrec_to_block = {}
    with zipfile.ZipFile(path) as archive:
        with io.TextIOWrapper(archive.open("pageo2020.pl"), encoding="utf-8") as handle:
            for row in csv.reader(handle, delimiter="|"):
                if len(row) <= 34 or row[2] != "750":
                    continue
                block = f"{row[12]}{row[14]}{row[32]}{row[34]}"
                if len(block) == 15:
                    logrec_to_block[row[7]] = block
        result = {}
        with io.TextIOWrapper(archive.open("pa000022020.pl"), encoding="utf-8") as handle:
            for row in csv.reader(handle, delimiter="|"):
                if len(row) > 5 and row[4] in logrec_to_block:
                    result[logrec_to_block[row[4]]] = int(row[5] or 0)  # P0030001
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_zip", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--allow-nonofficial-hash", action="store_true")
    args = parser.parse_args()
    actual_hash = sha256(args.source_zip)
    if actual_hash != OFFICIAL_SHA256 and not args.allow_nonofficial_hash:
        raise RuntimeError(f"Unexpected source SHA-256: {actual_hash}")
    rows = load_block_vap(args.source_zip)
    if len(rows) != 336985:
        raise RuntimeError(f"Expected 336,985 Pennsylvania blocks, found {len(rows):,}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Fix the gzip timestamp and omit the source filename so rebuilding the
    # same official input produces the same bytes on every machine and date.
    with args.output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, lineterminator="\n")
                writer.writerow(("block", "vap"))
                writer.writerows(sorted(rows.items()))
    print({
        "source_url": SOURCE_URL,
        "source_sha256": actual_hash,
        "blocks": len(rows),
        "vap_total": sum(rows.values()),
        "output": str(args.output),
        "output_sha256": sha256(args.output),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

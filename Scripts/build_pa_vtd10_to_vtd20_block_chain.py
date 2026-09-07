"""Build a Pennsylvania VTD10-to-VTD20 chain from Census block relationships."""

from __future__ import annotations

import csv
import io
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
VTD10_ZIP = DATA / "tl_2012_42_vtd10.zip"
BLOCK10_ZIP = DATA / "tl_2020_42_tabblock10.zip"
BLOCK_REL_ZIP = DATA / "nhgis_blk2010_blk2020_42.zip"
BLOCK_ASSIGN_ZIP = DATA / "BlockAssign_ST42_PA.zip"
OUTPUT = DATA / "crosswalks" / "pa_vtd10_to_vtd20_block_chain.csv"
VTD10_URL = "https://www2.census.gov/geo/tiger/TIGER2012/VTD/tl_2012_42_vtd10.zip"


def digits(value: object, width: int) -> str:
    text = "".join(ch for ch in str(value or "") if ch.isdigit())
    return text.zfill(width) if text else ""


def ensure_vtd10() -> None:
    if VTD10_ZIP.exists():
        return
    print(f"downloading {VTD10_URL}")
    with urllib.request.urlopen(VTD10_URL, timeout=120) as response:
        VTD10_ZIP.write_bytes(response.read())


def block20_vtd_index() -> dict[str, tuple[str, str]]:
    result = {}
    with zipfile.ZipFile(BLOCK_ASSIGN_ZIP) as archive:
        name = next(name for name in archive.namelist() if name.upper().endswith("_VTD.TXT"))
        with archive.open(name) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8-sig")
            reader = csv.DictReader(text, delimiter="|")
            for row in reader:
                block = digits(row.get("BLOCKID"), 15)
                county = digits(row.get("COUNTYFP"), 3)
                vtd = "".join(ch for ch in str(row.get("VTD") or row.get("DISTRICT") or "").upper() if ch.isalnum()).zfill(6)
                if block and county and vtd:
                    result[block] = (county, vtd)
    return result


def main() -> None:
    ensure_vtd10()
    vtds = gpd.read_file(f"zip://{VTD10_ZIP.resolve()}", columns=["COUNTYFP10", "VTDST10", "geometry"])
    blocks = gpd.read_file(f"zip://{BLOCK10_ZIP.resolve()}", columns=["GEOID10", "COUNTYFP10", "geometry"])
    blocks = blocks.to_crs(vtds.crs)
    points = blocks[["GEOID10", "COUNTYFP10", "geometry"]].copy()
    points["geometry"] = points.geometry.representative_point()
    joined = gpd.sjoin(points, vtds, how="left", predicate="within")
    block10_to_vtd10 = {
        digits(row.GEOID10, 15): (digits(row.COUNTYFP10_left, 3), str(row.VTDST10 or "").strip().upper().zfill(6))
        for row in joined.itertuples()
        if getattr(row, "index_right", None) == getattr(row, "index_right", None)
    }

    with zipfile.ZipFile(BLOCK_REL_ZIP) as archive:
        name = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
        with archive.open(name) as raw:
            relationships = pd.read_csv(raw, dtype=str)
    vtd20_by_block = block20_vtd_index()
    weights: dict[tuple[str, str], dict[tuple[str, str], float]] = defaultdict(lambda: defaultdict(float))
    for row in relationships.itertuples(index=False):
        block10 = digits(row.blk2010ge, 15)
        block20 = digits(row.blk2020ge, 15)
        source = block10_to_vtd10.get(block10)
        target = vtd20_by_block.get(block20)
        weight = float(row.weight or 0)
        if source and target and source[0] == target[0] and weight > 0:
            weights[source][target] += weight

    rows = []
    for (county, src_vtd), targets in sorted(weights.items()):
        total = sum(targets.values()) or 1.0
        for (dst_county, dst_vtd), weight in sorted(targets.items()):
            rows.append({
                "countyfp": county,
                "src_vtd": src_vtd,
                "dst_countyfp": dst_county,
                "dst_vtd": dst_vtd,
                "weight": f"{weight / total:.12f}",
                "method": "census_block_relationship_count",
            })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["countyfp", "src_vtd", "dst_countyfp", "dst_vtd", "weight", "method"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):,} rows for {len(weights):,} VTD10 sources to {OUTPUT}")


if __name__ == "__main__":
    main()

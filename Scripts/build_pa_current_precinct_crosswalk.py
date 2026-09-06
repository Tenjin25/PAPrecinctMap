"""Build a VTD20-to-current-precinct crosswalk.

The historical/modern election crosswalks target the VTD20 layer, while the
frontend displays ``pa_current_voting_districts.geojson``.  This bridge maps
each VTD20 target onto the actual current precinct polygons.  Census blocks
are the preferred disaggregation unit when a VTD20 was split into multiple
current precincts; polygon overlap is retained only as a last-resort fallback.
"""

from __future__ import annotations

import csv
import zipfile
from collections import defaultdict
from pathlib import Path

import geopandas as gpd


BASE = Path(__file__).resolve().parents[1]
DATA = BASE / "data"
OLD_GEOMETRY = DATA / "Voting_Precincts.geojson"
CURRENT_GEOMETRY = DATA / "pa_current_voting_districts.geojson"
OUTPUT = DATA / "crosswalks" / "pa_vtd20_to_current_precinct.csv"
BLOCK_GEOMETRY = DATA / "tl_2022_42_tabblock20.zip"
BLOCK_ASSIGNMENTS = DATA / "BlockAssign_ST42_PA.zip"
BLOCK_ASSIGNMENT_MEMBER = "BlockAssign_ST42_PA_VTD.txt"


def norm(value: object, width: int = 0) -> str:
    text = "" if value is None else str(value).strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(width) if digits else ""


def load_block_vtd_assignments() -> dict[str, tuple[str, str]]:
    """Return 2020 census block -> (county, VTD20) assignments."""
    result = {}
    with zipfile.ZipFile(BLOCK_ASSIGNMENTS) as archive:
        with archive.open(BLOCK_ASSIGNMENT_MEMBER) as raw:
            header = raw.readline().decode("utf-8-sig").rstrip("\r\n").split("|")
            columns = {name.strip().upper(): i for i, name in enumerate(header)}
            block_idx = columns.get("BLOCKID")
            county_idx = columns.get("COUNTYFP")
            vtd_idx = columns.get("VTD")
            if vtd_idx is None:
                vtd_idx = columns.get("DISTRICT")
            if block_idx is None or county_idx is None or vtd_idx is None:
                raise ValueError(f"unexpected block assignment columns: {header}")
            for encoded in raw:
                parts = encoded.decode("utf-8", errors="ignore").rstrip("\r\n").split("|")
                if len(parts) <= max(block_idx, county_idx, vtd_idx):
                    continue
                block = norm(parts[block_idx], 15)
                county = norm(parts[county_idx], 3)
                vtd = norm(parts[vtd_idx], 6)
                if block and county and vtd:
                    result[block] = (county, vtd)
    return result


def build_block_weights(current: gpd.GeoDataFrame) -> dict[tuple[str, str], dict[int, int]]:
    """Count disaggregated census blocks in each current-precinct target."""
    assignments = load_block_vtd_assignments()
    blocks = gpd.read_file(f"zip://{BLOCK_GEOMETRY.resolve()}", columns=["GEOID20", "geometry"])
    blocks = blocks.to_crs(current.crs)
    # Representative points avoid duplicating a block when polygon boundaries
    # merely touch and are substantially cheaper than full overlay geometry.
    points = blocks[["GEOID20", "geometry"]].copy()
    points["geometry"] = points.geometry.representative_point()
    joined = gpd.sjoin(points, current[["geometry"]], how="left", predicate="within")
    counts: dict[tuple[str, str], dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for row in joined.itertuples():
        assignment = assignments.get(norm(row.GEOID20, 15))
        target_idx = getattr(row, "index_right", None)
        if assignment and target_idx is not None and target_idx == target_idx:
            counts[assignment][int(target_idx)] += 1
    return counts


def main() -> None:
    old = gpd.read_file(OLD_GEOMETRY).to_crs(5070)
    current = gpd.read_file(CURRENT_GEOMETRY).to_crs(5070)
    old["countyfp"] = old["COUNTYFP20"].map(lambda v: norm(v, 3))
    old["vtd20"] = old["VTD"].map(lambda v: norm(v, 6))
    old = old[old["countyfp"].ne("") & old["vtd20"].ne("")]
    # TIGER can contain multipart VTD records with the same county/VTD key.
    # Treat that key as one source precinct so its allocation is emitted once.
    old = old[["countyfp", "vtd20", "geometry"]].dissolve(
        by=["countyfp", "vtd20"], as_index=False
    )
    current["countyfp"] = current["COUNTYFP"].map(lambda v: norm(v, 3))
    current["vtd"] = current["VTD"].map(lambda v: norm(v, 6))
    current["vtd20"] = current["VTD20"].map(lambda v: norm(v, 6))
    current["precinct_norm"] = current["precinct_norm"].astype(str).str.upper().str.strip()

    direct = {}
    for row in current.itertuples():
        if row.countyfp and row.vtd20 and row.precinct_norm:
            direct.setdefault((row.countyfp, row.vtd20), []).append((row.countyfp, row.vtd, row.precinct_norm))

    block_weights = build_block_weights(current)

    spatial_index = current.sindex
    rows = []
    unmatched = []
    for old_row in old.itertuples():
        key = (old_row.countyfp, old_row.vtd20)
        direct_targets = direct.get(key, [])
        # A VTD20 identifier can be copied onto several newer precinct pieces.
        # Giving every piece weight 1 duplicates the election returns.  Keep
        # identity only when it is genuinely one-to-one; otherwise allocate by
        # the underlying block assignments below.
        if len(direct_targets) == 1:
            for countyfp, vtd, precinct_norm in direct_targets:
                rows.append({
                    "countyfp": old_row.countyfp,
                    "vtd20": old_row.vtd20,
                    "current_countyfp": countyfp,
                    "current_vtd": vtd,
                    "current_precinct_norm": precinct_norm,
                    "weight": "1.000000000000",
                    "method": "vtd20_identity",
                })
            continue

        block_targets = block_weights.get(key, {})
        if block_targets:
            total_blocks = sum(block_targets.values())
            for target_idx, block_count in sorted(block_targets.items()):
                current_row = current.loc[target_idx]
                rows.append({
                    "countyfp": old_row.countyfp,
                    "vtd20": old_row.vtd20,
                    "current_countyfp": current_row["countyfp"],
                    "current_vtd": current_row["vtd"],
                    "current_precinct_norm": current_row["precinct_norm"],
                    "weight": f"{block_count / total_blocks:.12f}",
                    "method": "census_block_count",
                })
            continue

        candidates = spatial_index.query(old_row.geometry, predicate="intersects")
        overlaps = []
        for idx in candidates:
            current_row = current.iloc[idx]
            if current_row["countyfp"] != old_row.countyfp:
                continue
            area = old_row.geometry.intersection(current_row.geometry).area
            if area > 0 and current_row["precinct_norm"]:
                overlaps.append((current_row["countyfp"], current_row["vtd"], current_row["precinct_norm"], area))
        total = sum(item[3] for item in overlaps)
        if total <= 0:
            unmatched.append(key)
            continue
        for countyfp, vtd, precinct_norm, area in overlaps:
            rows.append({
                "countyfp": old_row.countyfp,
                "vtd20": old_row.vtd20,
                "current_countyfp": countyfp,
                "current_vtd": vtd,
                "current_precinct_norm": precinct_norm,
                "weight": f"{area / total:.12f}",
                "method": "geometry_overlap",
            })

    sums = defaultdict(float)
    for row in rows:
        sums[(row["countyfp"], row["vtd20"])] += float(row["weight"])
    bad_sums = [key for key, value in sums.items() if abs(value - 1.0) > 1e-6]
    if bad_sums:
        raise RuntimeError(f"{len(bad_sums):,} VTD20 crosswalk weights do not sum to 1")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "countyfp", "vtd20", "current_countyfp", "current_vtd",
            "current_precinct_norm", "weight", "method",
        ])
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows):,} bridge rows for {len(set((r['countyfp'], r['vtd20']) for r in rows)):,} VTD20 precincts")
    print(f"unmatched VTD20 precincts: {len(unmatched):,}")


if __name__ == "__main__":
    main()

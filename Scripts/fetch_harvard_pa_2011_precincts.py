"""Download the Harvard Election Data Archive Pennsylvania precinct layer."""
from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "data" / "historical_sources" / "harvard_pa_2011"
ARCHIVE = DESTINATION / "PA_Shapefile.zip"
URL = "https://dataverse.harvard.edu/api/access/datafile/2301832"
SHA256 = "8ed1d00554a683e7a5f97c4ff08957bc9ee91f0e21944d6b29e4298c8e298790"


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE.exists() or hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != SHA256:
        urllib.request.urlretrieve(URL, ARCHIVE)
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest != SHA256:
        raise RuntimeError(f"Unexpected archive checksum: {digest}")
    with zipfile.ZipFile(ARCHIVE) as source:
        source.extractall(DESTINATION / "extracted")
    print(DESTINATION / "extracted" / "pa_final.shp")


if __name__ == "__main__":
    main()

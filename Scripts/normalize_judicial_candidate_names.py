"""Normalize judicial candidate labels in generated JSON artifacts.

The Pennsylvania source exports vary in capitalization, punctuation, and the
encoding used for retention-question separators.  This keeps published JSON
human-readable without changing any vote fields.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JUDICIAL_GLOBS = (
    ROOT / "data" / "contests",
    ROOT / "data" / "district_contests",
)


def format_name(name: str) -> str:
    """Return a consistently cased personal name, preserving initials."""
    words = []
    for raw_word in re.split(r"\s+", name.strip()):
        if not raw_word:
            continue
        bare = raw_word.rstrip(".")
        upper = bare.upper()
        if upper in {"JR", "SR"}:
            words.append(f"{upper.title()}.")
            continue
        if upper in {"II", "III", "IV", "V", "VI"}:
            words.append(upper)
            continue
        if len(bare) == 1 and bare.isalpha():
            words.append(f"{bare.upper()}.")
            continue
        pieces = []
        for piece in raw_word.split("-"):
            titled = piece[:1].upper() + piece[1:].lower()
            if len(titled) > 3 and titled.lower().startswith("mc"):
                titled = "Mc" + titled[2:3].upper() + titled[3:]
            pieces.append(titled)
        words.append("-".join(pieces))
    return " ".join(words)


def normalize_candidate_label(value: str) -> str:
    value = re.sub(r"\s+", " ", str(value or "").strip())
    if not value:
        return ""

    # Normalize malformed Windows-1252/em-dash retention separators before
    # treating the remaining text as a personal name.
    retention = re.match(r"^(Yes|No)\s+(?:—|�|\x96)\s+(.+)$", value, re.I)
    if retention:
        return f"{retention.group(1).title()} — {format_name(retention.group(2))}"
    return " / ".join(format_name(part) for part in value.split("/") if part.strip())


def normalize_value(value):
    if isinstance(value, dict):
        return {key: normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def normalize_document(document):
    if isinstance(document, dict):
        out = {}
        for key, value in document.items():
            if key in {"dem_candidate", "rep_candidate"} and isinstance(value, str):
                out[key] = normalize_candidate_label(value)
            else:
                out[key] = normalize_document(value)
        return out
    if isinstance(document, list):
        return [normalize_document(item) for item in document]
    return document


def main() -> int:
    paths = [path for directory in JUDICIAL_GLOBS for path in directory.glob("*court*.json")]
    paths.append(ROOT / "data" / "pa_elections_aggregated.json")
    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        normalized = normalize_document(document)
        path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Normalized candidate labels and formatted {len(paths)} JSON files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

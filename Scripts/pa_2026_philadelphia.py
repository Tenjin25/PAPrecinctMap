"""Read Philadelphia's archived 2026 division workbook without altering it."""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl


WORKBOOK = Path(__file__).resolve().parents[1] / "data/source_reports/2026_general/philadelphia.xlsx"
METHODS = ("Election Day", "Mail Votes", "Provisional")


def load_philadelphia() -> tuple[tuple, list[tuple[str, tuple, tuple]]]:
    book = openpyxl.load_workbook(WORKBOOK, read_only=True, data_only=True)
    try:
        totals = book["Totals"].values
        headers = next(totals)
        by_type = book["By_Type"].values
        if tuple(next(by_type)[2:]) != tuple(headers[1:]):
            raise ValueError("Philadelphia workbook headings differ between sheets")
        methods = {}
        for row in by_type:
            if row[1] in METHODS and row[0]:
                key = (row[0], row[1])
                if key in methods:
                    raise ValueError(f"Duplicate Philadelphia vote method: {key}")
                methods[key] = row
        result = []
        for row in totals:
            precinct = row[0]
            if precinct == "COUNTY TOTALS":
                county_total = row
                continue
            if not re.fullmatch(r"\d{2}-\d{2}", str(precinct)) and precinct not in {
                "2nd Congressional", "3rd Congressional", "5th Congressional"
            }:
                raise ValueError(f"Unknown Philadelphia result row: {precinct}")
            vote_methods = tuple(methods.get((precinct, method)) for method in METHODS)
            for col in range(9, 85):
                if int(row[col] or 0) != sum(int(method_row[col + 1] or 0) for method_row in vote_methods if method_row):
                    raise ValueError(f"Philadelphia vote methods differ: {precinct}, column {col}")
            result.append((precinct, row, vote_methods))
        if len(result) != 1706 or sum(re.fullmatch(r"\d{2}-\d{2}", str(name)) is not None for name, *_ in result) != 1703:
            raise ValueError("Philadelphia division count changed")
        for col in range(9, 13):
            if sum(int(row[col] or 0) for _, row, _ in result) != int(county_total[col] or 0):
                raise ValueError(f"Philadelphia governor county total differs: column {col}")
        return headers, result
    finally:
        book.close()

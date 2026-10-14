#!/usr/bin/env python3
"""Regression tests for county-clustered district vote aggregation."""

from __future__ import annotations

import json
import sys
import unittest
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Scripts"))

import build_county_clustered_2024_district_contests as clustered


class CountyRuleTests(unittest.TestCase):
    def test_999_percent_is_whole_county(self):
        self.assertEqual(clustered.classify_county_weights({"8": 999, "7": 1}), {"8"})

    def test_below_999_percent_keeps_material_split(self):
        self.assertEqual(
            clustered.classify_county_weights({"8": 998.9, "7": 1.1}),
            {"7", "8"},
        )

    def test_point_one_percent_or_less_is_a_sliver(self):
        self.assertEqual(
            clustered.classify_county_weights({"8": 500, "9": 499.5, "7": 0.5}),
            {"8", "9"},
        )

    def test_congressional_mail_labels_stay_local(self):
        for label in ("1ST CD", "2ND CD", "3RD CD", "11TH CD"):
            with self.subTest(label=label):
                self.assertEqual(
                    clustered.congressional_mail_district(label),
                    str(int("".join(char for char in label if char.isdigit()))),
                )
        self.assertEqual(clustered.congressional_mail_district("Congressional Mail Votes"), "")

    def test_fractional_rows_integerize_within_county_party(self):
        rows = [
            {"county": "Monroe", "office": "President", "party": "DEM", "candidate": "A", "votes": "4.4"},
            {"county": "Monroe", "office": "President", "party": "DEM", "candidate": "A", "votes": "5.6"},
            {"county": "Luzerne", "office": "President", "party": "DEM", "candidate": "A", "votes": "2.5"},
            {"county": "Luzerne", "office": "President", "party": "DEM", "candidate": "A", "votes": "2.5"},
        ]
        result = clustered.integerize_fractional_rows(rows)
        self.assertEqual([int(row["votes"]) for row in result], [4, 6, 3, 2])
        self.assertEqual(sum(int(row["votes"]) for row in result[:2]), 10)
        self.assertEqual(sum(int(row["votes"]) for row in result[2:]), 5)


class PublishedDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = ROOT / "data" / "district_contests"
        cls.payloads = []
        for path in cls.directory.glob("*.json"):
            if path.name != "manifest.json":
                cls.payloads.append((path, json.loads(path.read_text(encoding="utf-8"))))

    @staticmethod
    def totals(payload):
        rows = payload["general"]["results"].values()
        return tuple(
            sum(int(row.get(field) or 0) for row in rows)
            for field in ("dem_votes", "rep_votes", "other_votes", "total_votes")
        )

    def test_every_result_has_component_conservation(self):
        for path, payload in self.payloads:
            with self.subTest(path=path.name):
                dem, rep, other, total = self.totals(payload)
                self.assertEqual(dem + rep + other, total)

    def test_scopes_have_identical_statewide_party_totals(self):
        groups = defaultdict(dict)
        for path, payload in self.payloads:
            key = (payload["year"], payload["contest_type"])
            groups[key][payload["scope"]] = self.totals(payload)
        for key, scopes in groups.items():
            if set(scopes) != {"congressional", "state_house", "state_senate"}:
                continue
            with self.subTest(year=key[0], contest=key[1]):
                self.assertEqual(len(set(scopes.values())), 1)

    def test_pa08_2024_us_senate_is_fixed(self):
        path = self.directory / "congressional_us_senate_2024.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = payload["general"]["results"]["8"]
        self.assertEqual(
            (row["dem_votes"], row["rep_votes"], row["other_votes"], row["total_votes"]),
            (180743, 198221, 8976, 387940),
        )
        self.assertEqual(row["dem_candidate"], "Bob Casey, Jr.")
        self.assertEqual(row["rep_candidate"], "David H. McCormick")

    def test_pa10_2018_us_senate_is_fixed(self):
        path = self.directory / "congressional_us_senate_2018.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        row = payload["general"]["results"]["10"]
        self.assertEqual(
            (row["dem_votes"], row["rep_votes"], row["other_votes"], row["total_votes"]),
            (144963, 143119, 5933, 294015),
        )
        self.assertAlmostEqual(row["margin_pct"], 0.627179, places=6)
        self.assertEqual(row["dem_candidate"], "Bob Casey, Jr.")
        self.assertEqual(row["rep_candidate"], "Lou Barletta")

    def test_2018_us_senate_matches_official_statewide_control(self):
        # PA's official API percentage denominator is the four named
        # candidates; its separate 1,568 write-ins are not party votes.
        expected = (2792437, 2134848, 82115, 5009400)
        for scope in ("congressional", "state_house", "state_senate"):
            path = self.directory / f"{scope}_us_senate_2018.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            with self.subTest(scope=scope):
                self.assertEqual(self.totals(payload), expected)

    def test_2018_us_senate_counties_match_official_control(self):
        payload = json.loads((ROOT / "data" / "contests" / "us_senate_2018.json").read_text(encoding="utf-8"))
        rows = payload["rows"]
        totals = tuple(sum(int(row[field]) for row in rows) for field in ("dem_votes", "rep_votes", "other_votes", "total_votes"))
        self.assertEqual(totals, (2792437, 2134848, 82115, 5009400))
        westmoreland = next(row for row in rows if row["county"] == "WESTMORELAND")
        self.assertEqual(
            (westmoreland["dem_votes"], westmoreland["rep_votes"], westmoreland["other_votes"], westmoreland["total_votes"]),
            (63778, 79078, 2402, 145258),
        )
        self.assertTrue(all(row["dem_candidate"] == "Bob Casey, Jr." for row in rows))

    def test_calibrated_layers_conserve_by_party(self):
        for contest, year in (("president", 2008), ("president", 2012),
                              ("governor", 2018), ("us_senate", 2018)):
            totals = {}
            for scope in ("congressional", "state_house", "state_senate"):
                path = self.directory / f"{scope}_{contest}_{year}.json"
                totals[scope] = self.totals(json.loads(path.read_text(encoding="utf-8")))
            with self.subTest(contest=contest, year=year):
                self.assertEqual(len(set(totals.values())), 1, totals)


if __name__ == "__main__":
    unittest.main()

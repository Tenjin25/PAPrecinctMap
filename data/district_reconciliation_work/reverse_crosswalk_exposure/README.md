# All-year reverse-crosswalk exposure

Regenerate with `audit_reverse_crosswalk_exposure.py`. The inventory finds
121 cross-boundary current-precinct/scope keys in 23 counties: 14 congressional,
81 House, and 26 Senate. Stored normalized files have exposed rows in 23
election years from 2000 through 2025.

`cross_boundary_keys.csv` retains forward crosswalk shares and source-VTD VAP
by district. `year_contest_scope_county_exposure.csv` groups exposed source
rows and source vote quantities by year, contest, scope, county, and party.
Those quantities are **not vote differences** and must not be added together
across scopes as distinct ballots. A key may have a maintained mapping that
preempts the reverse fallback; each source path must be replayed to adjudicate
an error. Whole-county VAP clamping is preserved in the inventory maps.

No production files are changed. No inverse-share reweighting is proposed:
forward population shares are not an invertible vote-allocation matrix.

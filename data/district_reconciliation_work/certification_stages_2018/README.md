# 2018 Senate certification-stage reconciliation

No production vote changes are proposed by this diagnostic.

All 270 current-decade district rows reproduce exactly as retained post-DRA
votes plus the retained localized Westmoreland certification deltas. Independently
allocating the normalized Westmoreland source rows with the existing Carter/VAP
geography reproduces both the pre-certification district totals (without controls)
and the generic candidate totals (with controls), across all three scopes, with
zero unmatched rows and exact county-party conservation.

The source named-candidate totals are D 63,956 / R 79,379 / Other 2,413;
certified controls are D 63,778 / R 79,078 / Other 2,402. Write-ins are excluded
consistently with the retained certification benchmark. Other counties are held
unchanged using the candidate's recorded county allocations, not a statewide
residual distribution.

The eleven previously partial DRA explanations have 27 party-level residuals.
They are the paired effect of applying county certification before precinct
allocation versus the retained localized adjustment after DRA calibration.
This does not independently validate DRA geography, nor prove either district
model superior. County-aggregate fractional integerization was also tested; it
does NOT reproduce the retained pre-certification district results (absolute
party-vote mismatches: congressional 2, House 16, Senate 14).

Reproduce from the repository root, in order:

    python data/district_reconciliation_work/reconcile_2018_certification_stages.py
    python data/district_reconciliation_work/replay_westmoreland_2018.py
    python data/district_reconciliation_work/audit_calibration_causes.py

The source-row allocation table identifies CSV source row, precinct, candidate,
VTD targets, district VAP weights, and allocated votes. The district-stage ledger
separates DRA, localized certification, and the candidate. These are provenance
tables, not observed block-level ballots or official fragment tallies.

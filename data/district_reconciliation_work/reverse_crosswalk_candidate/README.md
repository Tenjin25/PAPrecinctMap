# Share-preserving reverse-crosswalk candidate: 2016 batch

This isolated replay identifies rows that actually reach the canonical current-
precinct fallback after maintained mappings have had precedence. It does not
classify all rows whose precinct keys are merely exposed.

For the 2016 normalized statewide source, 32,989 positive-vote source rows use
a share-sensitive canonical fallback. Of those, 3,170 unique source rows change
at least one scope after the retained forward shares are applied to source-VTD
VAP. They produce 3,929 affected source-row/scope records, 505 changed generic-
candidate district rows, and 180 year/contest/scope/county decision groups.

The legacy path treats every source VTD in the reverse union as weight 1.0. The
candidate instead computes each district weight as:

    sum(source VTD district VAP * retained source-VTD-to-current-precinct share)

It then uses the existing deterministic largest-remainder allocator. All paired
county/party transfers conserve exactly. The same Carter bridge, Census block
VAP, current-plan BEFs, and VAP-based 99.9% whole-county clamp are used. No
unexplained vote is introduced or distributed statewide.

## Evidence

- `affected_source_rows.csv`: source file/index, precinct, candidate, party,
  old and corrected VTD targets, district VAP, and integer allocations.
- `county_district_party_transfers.csv`: every paired county/district/party
  transfer.
- `district_change_candidate.csv`: generic before/after rows and current
  publication values.
- `county_party_conservation.csv`: exact old-versus-corrected controls.
- `decision_ledger.csv`: grouped decision class and disposition.
- `input_fingerprints.json`: retained source, crosswalk, VAP, BEF and
  publication fingerprints. The generic candidate is rebuilt in a temporary
  directory and is never promoted or required from an untracked workspace.

## Production decision

No production vote change is proposed. Forward-share weighting repairs the
demonstrated numerical fallback defect, but scalar precinct shares do not by
themselves independently validate fragment geography. Existing reviewed Emmaus
corrections supersede this generic candidate. Districts 131 and 134 are marked
as mixed with that review and require a full reconstructed pipeline; the delta
must never be layered onto the corrected publication. The same restriction
applies to any calibrated layer.

Reproduce this batch from the repository root:

    python data/district_reconciliation_work/audit_reverse_crosswalk_candidate.py 2016
    python -m unittest data.district_reconciliation_work.test_reverse_crosswalk_candidate

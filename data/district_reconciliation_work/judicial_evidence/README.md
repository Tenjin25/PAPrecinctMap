# Legacy judicial county/allocation evidence recovery

The acceptance baseline listed 33 congressional/House/Senate files with no
county or allocation receipt. This diagnostic bypasses the county-contest
manifest only when explicitly requested; the production default remains
fail-closed. It reads retained official precinct exports, integerizes fractional
source rows once, and allocates them through the same Carter/VAP/current-BEF
path used by the candidate builder. Published district totals are never an
input.

Evidence is recovered for 27 of 33 files with zero unmatched rows, zero
unallocated rows, and zero county-conservation failures. The compact county-to-
district ledger contains 3,626 allocation rows. The reconstructed source also
changes 2,014 district rows relative to the prior candidate and changes 144
candidate-label strings, so none of these files is approved for production.
The label changes must be reviewed as identities/orderings and preserved before
any future promotion.

Six files remain blocked: all three scopes for 2019 Commonwealth Court and 2025
Supreme Court. The retained official exports contain no rows for those contests;
they contain 2019 Commonwealth retention races and 2025 Supreme retention races
instead. No evidence was synthesized from the published district totals.

Artifacts:

- `recovery_ledger.csv`: file-level source, allocation and conservation gates.
- `county_district_allocations.csv`: auditable county-to-district party records.
- `district_vote_changes.csv`: prior-candidate versus recovered-source rows.
- `candidate_name_changes.csv`: labels requiring preservation review.
- `input_fingerprints.json`: retained official-source fingerprints.

Reproduce:

    python data/district_reconciliation_work/recover_judicial_evidence.py 2001 2003 2011 2015 2019 2021 2025

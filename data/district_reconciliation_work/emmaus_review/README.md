# Reviewed Emmaus 2016 evidence

This is the only promoted subset of the broader reconciliation. See
`../report/RELEASE.md` for the decision and exact scope.

- `official_candidate_rows.csv`: 108 original official source rows, physical
  line numbers, municipality type, original labels, candidate names and votes.
- `original_precinct_block_witness.csv`: all 401 original 2016 Emmaus blocks
  across the six election precincts, independently assigned to current HD-134.
- `proposed_district_changes.csv`: all ten before/after district rows, reported
  before promotion; every party transfer is paired within Lehigh County.
- `data/benchmarks/reviewed_emmaus_2016.json`: source fingerprints, exact
  precinct transfers, full original county evidence and before/after layer
  hashes. The original archive SHA-256 is retained without committing the ZIP.

`prepare_emmaus_review.py` generates the package against the original,
unmodified baseline and supplied archive. It intentionally rejects a changed
baseline. It is not a command to rerun blindly after publication. Production
rebuilds use the source-bound reviewed correction, not the exploratory scripts.

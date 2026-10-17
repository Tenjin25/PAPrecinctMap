# Conserved substitution preview — not approved for promotion

Pre-release diagnostic snapshot: this 143-row package is not promoted. Only
the separately reviewed ten-row Emmaus subset is released; see `../report/RELEASE.md`.
Do not apply these preview deltas on top of the reviewed production values.

Regenerate with `preview_source_backed_hybrid.py` after the priority-county
source audits. The script never writes production data.

198 county/contest/scope slices were reviewed; 69 meet all arithmetic/source
prerequisites. Substituting those slices produces 143 changed district rows in
19 layers, listed individually in `district_change_preview.csv`. Every proposed
county transfer is paired by party and every layer has zero statewide-party
delta. Published candidate names are not edited.

Eligibility requires exact original-source versus certified county controls,
zero unmatched rows including zero-vote rows, exact county-party conservation,
and reproduction of every published district-party value by the baseline.
Layers that already contain calibration differences are blocked: their generic
candidate county components must not be treated as published components.

These prerequisites do not establish geographic correctness. Original RDH block
assignments are modeled and can cross named administrative boundaries. The
independent HD-134 legal-membership benchmark demonstrates such a small
disagreement. Consequently no preview row is approved for promotion.

`county_slice_review.csv` records blocked slices and each prerequisite;
`county_district_party_transfers.csv` records exact paired contributions;
`conservation_audit.csv` records each layer's zero party delta.

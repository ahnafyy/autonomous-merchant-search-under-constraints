# Claim Taxonomy

Every substantive result belongs in `research/claims.yml` before it appears as a
finding. Use the narrowest status supported by the evidence.

| Status | Appropriate evidence | Required language |
| --- | --- | --- |
| `analytic` | A proof represented in the manuscript | State assumptions and cite the theorem or proposition label |
| `exact-computational` | Exhaustive or exact arithmetic with an executable evaluator | State the finite domain and exact procedure |
| `numerical` | Approximation with an executable evaluator | State tolerance, precision, seed where relevant, and tested domain |
| `computational-pattern` | Repeated finite observations | State the grid or sample; do not imply a theorem |
| `conjecture` | A precise unsupported generalization | Label it explicitly and retain known supporting and adverse evidence |
| `open` | A question not resolved by current evidence | State what remains unknown |

Computed claims name an evaluator as `module:function`. An evaluator receives the
analysis result dictionary and the claim record, then returns `passed`, `observed`,
`expected`, and a plain-language `detail`. A failing evaluator must fail the build; it
must not silently downgrade or rewrite the claim.

`scope` records where the statement applies. `limitations` records assumptions and
known boundaries. `site_visible` controls public display after initialization; private
fixture claims remain visible only while the repository is in template mode.

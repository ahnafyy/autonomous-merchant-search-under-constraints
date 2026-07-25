---
description: "Claim-aware LaTeX rules for the arXiv manuscript and generated tables."
applyTo: "paper/**/*.tex"
---

- Reference public findings by their stable claim ID in source comments.
- Read headline values from generated macros or tables; never type them independently.
- State assumptions and claim status close to the result they qualify.
- Keep the package set conservative and compatible with arXiv compilation.
- Do not edit files under `paper/generated/`; rebuild them from verified artifacts.

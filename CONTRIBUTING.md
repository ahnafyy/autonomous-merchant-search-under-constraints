# Contributing

Changes must preserve the evidence architecture: study values originate in
`packages/python/`, flow through `paperkit build`, and are consumed from `artifacts/`
by the paper and site. The npm implementation must pass generated conformance vectors.
Do not duplicate scientific constants in package tests or publication code.

Before opening a pull request, run:

```bash
python -m ruff check .
python -m pytest
paperkit validate
paperkit build
npm ci --prefix packages/javascript
npm test --prefix packages/javascript
npm run pack:check --prefix packages/javascript
npm ci --prefix site
npm run check --prefix site
npm run build --prefix site
npm run test:e2e --prefix site
```

Use `python -m pytest` so the tests run under the selected virtual environment. Keep
changes focused, deterministic, and covered at the narrowest useful level. Never invent
citations or mark a human gate approved on another person's behalf.

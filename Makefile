.PHONY: venv install build packages paper site validate release test lint check collect-global-catalog analyze-global-catalog

PYTHON := .venv/bin/python
NODE := npx --yes node@22.12.0
GLOBAL_CATALOG_OUTPUT ?= data/ucp/raw/shopify-global-catalog-2026-09-17
GLOBAL_CATALOG_RESULTS ?= data/ucp/global-catalog-study-2026-09-17.json
GLOBAL_CATALOG_CONFIG ?= research/global-catalog-collection.json

venv: $(PYTHON)

$(PYTHON):
	python3 -m venv .venv

install: venv
	$(PYTHON) -m pip install -e '.[dev]'
	$(PYTHON) -m pip install -e packages/python
	npm ci --prefix packages/javascript
	npm ci --prefix site

build:
	$(PYTHON) -m paperkit.cli build

packages: build
	$(PYTHON) -m build packages/python
	npm test --prefix packages/javascript
	npm run pack:check --prefix packages/javascript

paper: build
	$(PYTHON) -m paperkit.cli build-paper

site: build
	$(NODE) site/scripts/sync-artifacts.mjs
	$(NODE) site/node_modules/astro/bin/astro.mjs build --root site

validate:
	$(PYTHON) -m paperkit.cli validate

collect-global-catalog:
	$(PYTHON) scripts/collect_global_catalog.py \
		--config $(GLOBAL_CATALOG_CONFIG) \
		--output-dir $(GLOBAL_CATALOG_OUTPUT)

analyze-global-catalog:
	$(PYTHON) scripts/analyze_global_catalog.py \
		--collection-dir $(GLOBAL_CATALOG_OUTPUT) \
		--analysis-config research/hidden-card-analysis.json \
		--output $(GLOBAL_CATALOG_RESULTS)

release:
	$(PYTHON) -m paperkit.cli release

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

check: lint test validate packages

.PHONY: venv install build packages paper site validate release test lint check

PYTHON := .venv/bin/python
NODE := npx --yes node@22.12.0

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

release:
	$(PYTHON) -m paperkit.cli release

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

check: lint test validate packages

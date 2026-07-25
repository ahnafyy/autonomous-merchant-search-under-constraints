.PHONY: install build packages paper site validate release test lint check

install:
	python -m pip install -e '.[dev]'
	python -m pip install -e packages/python
	npm ci --prefix packages/javascript

build:
	python -m paperkit.cli build

packages: build
	python -m build packages/python
	npm test --prefix packages/javascript
	npm run pack:check --prefix packages/javascript

paper: build
	python -m paperkit.cli build-paper

site: build
	npm run build --prefix site

validate:
	python -m paperkit.cli validate

release:
	python -m paperkit.cli release

test:
	python -m pytest

lint:
	python -m ruff check .

check: lint test validate packages

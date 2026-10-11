.PHONY: install test build build-offline metrics all

install:
	uv sync

test:
	uv run pytest -q

# Celý běh: stažení zdrojů (s diskovou cache), DB, exporty, ověřovací formulář.
build:
	uv run investors build

# Stejný běh čistě z cache (bez síťových požadavků) – reprodukovatelnost.
build-offline:
	uv run investors build --offline

# Po vyplnění verification/form_filled.csv
metrics:
	uv run investors metrics

all: install test build

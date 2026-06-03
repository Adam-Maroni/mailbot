.PHONY: build deploy logs status local backup test lint

# Build the mailbot-api Docker image. Full body lands in story 1-2.
build:
	@echo "[build] placeholder — full body in story 1-2 (docker compose build mailbot-api)"

# docker save + scp + docker load + rolling restart on VPS. Story 6-7.
# Requires MAILBOT_VPS_HOST env var; see scripts/deploy.sh.
deploy:
	@bash scripts/deploy.sh

# Tail the mailbot-api container logs. Full body lands in epic 6 (mailbot logs CLI).
logs:
	@echo "[logs] placeholder — full body in epic 6"

# mailbot status — VPS-side health snapshot. Full body lands in epic 6 (story 6-1).
status:
	@echo "[status] placeholder — full body in epic 6 (story 6-1)"

# Run the local dev stack (3-container compose with hot-reload bind mounts). Full body in story 1-2.
local:
	@echo "[local] placeholder — full body in story 1-2 (docker compose -f docker-compose.yml -f docker-compose.override.yml up)"

# Nightly SQLite .backup + config tarball. Story 6-7.
# Runs ON the VPS via cron; see scripts/backup.sh + docs/setup-vps-runbook.md §6.
backup:
	@bash scripts/backup.sh

# Python interpreter. Override on POSIX via: make PYTHON=.venv/bin/python test
PYTHON ?= .venv/Scripts/python.exe

# Run the test suite.
test:
	@$(PYTHON) -m pytest -q

# Lint + type-check the package.
lint:
	@$(PYTHON) -m ruff check .
	@$(PYTHON) -m mypy --strict mailbot_api/

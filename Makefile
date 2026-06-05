.PHONY: install run worker flush-worker lint format check test test-unit test-integration migrate db-upgrade db-downgrade ch-ddl smoke-video smoke-image smoke-text

install:
	uv sync

run:
	uv run uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8080} --reload

worker:
	uv run python -m app.workers.video_worker

flush-worker:
	uv run python -m app.workers.clickhouse_flush_worker

lint:
	uv run ruff check app tests scripts alembic

format:
	uv run ruff format app tests scripts alembic

check: lint test

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit

test-integration:
	uv run pytest tests/integration

migrate: db-upgrade

db-upgrade:
	uv run alembic upgrade head

db-downgrade:
	uv run alembic downgrade -1

ch-ddl:
	uv run python scripts/create_clickhouse_tables.py

smoke-video:
	uv run python scripts/smoke_video_detect.py

smoke-image:
	uv run python scripts/smoke_image_url.py

smoke-text:
	uv run python scripts/smoke_text.py

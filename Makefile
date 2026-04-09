.PHONY: up down logs migrate test shell dev

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	cd backend && alembic upgrade head

test:
	cd backend && pytest -v

shell:
	cd backend && python -m ipython

dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

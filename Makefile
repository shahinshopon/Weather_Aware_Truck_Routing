.PHONY: help install test lint run-backend run-frontend build

help:
	@echo "Available commands:"
	@echo "  make install       - Install backend and frontend dependencies"
	@echo "  make test          - Run backend and frontend test suites"
	@echo "  make lint          - Run ruff, mypy, and frontend typecheck"
	@echo "  make run-backend   - Start Django backend on port 8000"
	@echo "  make run-frontend  - Start Vite frontend on port 5173"
	@echo "  make build         - Build frontend production bundle"

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
	cd frontend && npm install

test:
	cd backend && .venv/bin/pytest --cov=risk --cov=scoring --cov=geometry
	cd frontend && npm run test -- --run

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/mypy risk scoring geometry
	cd frontend && npm run typecheck

run-backend:
	cd backend && .venv/bin/python manage.py runserver 8000

run-frontend:
	cd frontend && npm run dev

build:
	cd frontend && npm run build

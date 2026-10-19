PYTHON ?= python3
VENV := backend/.venv
VENV_BIN := $(VENV)/bin

.PHONY: install backend-install frontend-install backend-run frontend-dev \
	backend-test backend-check frontend-build frontend-lint frontend-test test

install: backend-install frontend-install

backend-install:
	test -d $(VENV) || $(PYTHON) -m venv $(VENV)
	$(VENV_BIN)/pip install -r backend/requirements.txt
	cd backend && .venv/bin/python manage.py migrate

frontend-install:
	cd frontend && npm install

backend-run:
	cd backend && .venv/bin/python manage.py runserver 8000

frontend-dev:
	cd frontend && npm run dev

backend-check:
	cd backend && .venv/bin/python manage.py check

backend-test:
	cd backend && .venv/bin/pytest

frontend-build:
	cd frontend && npm run build

frontend-lint:
	cd frontend && npm run lint

frontend-test:
	cd frontend && npm test

test: backend-check backend-test frontend-lint frontend-test frontend-build

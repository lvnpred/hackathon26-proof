PY := .venv/bin
export PYTHONPATH := backend

# Ports come from the .env shared with Doctor Dictation, at the workspace root.
-include ../.env
CG_API_PORT ?= 8100
CG_WEB_PORT ?= 5173
export CG_API_PORT CG_WEB_PORT

.PHONY: setup test eval day1 backend frontend dev

setup:
	python3 -m venv .venv
	$(PY)/pip install -r backend/requirements.txt
	cd frontend && npm install

test:
	$(PY)/pytest -q

eval:
	$(PY)/python eval/run_eval.py

day1:
	$(PY)/python -m app.day1

backend:
	$(PY)/uvicorn app.main:app --app-dir backend --reload --port $(CG_API_PORT)

frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 backend frontend

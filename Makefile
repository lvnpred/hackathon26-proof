PY := .venv/bin
export PYTHONPATH := backend

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
	$(PY)/uvicorn app.main:app --app-dir backend --reload --port 8000

frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 backend frontend

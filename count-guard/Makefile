PY := .venv/bin
export PYTHONPATH := backend

# Ports come from the .env shared with Doctor Dictation, at the workspace root.
-include ../.env
CG_API_PORT ?= 8100
CG_WEB_PORT ?= 5173
export CG_API_PORT CG_WEB_PORT

.PHONY: setup test eval day1 cost baseline backend frontend dev demo-check

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

# make cost CLIP=tray.mp4 -- prints the SAM 3.1 bill for one clip; no call.
cost:
	$(PY)/python -m app.spend $(CLIP)

# make baseline CLIP=tray.mp4 TRUTH=eval/ground_truth/clip2.json [SPEND=1]
baseline:
	$(PY)/python -m app.baseline $(CLIP) $(TRUTH) $(if $(SPEND),--spend)

backend:
	$(PY)/uvicorn app.main:app --app-dir backend --reload --port $(CG_API_PORT)

frontend:
	cd frontend && npm run dev

dev:
	$(MAKE) -j2 backend frontend

# Offline run of the demo script in a headless browser; starts its own servers on 8200 and 5273.
demo-check:
	$(PY)/python eval/p2/make_media.py
	$(PY)/python eval/p3/make_clips.py
	$(PY)/python eval/p4/make_photos.py
	cd frontend && node --test 'scripts/demo/*.test.mjs' && node scripts/demo/run.mjs

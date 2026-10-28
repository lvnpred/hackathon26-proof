# hackathon26 workspace: two apps, one repo, one .env, separate ports.
#   make setup   create both virtualenvs and install the frontend
#   make dev     run Doctor Dictation and Count Guard (API + web) together
#   make test    run both test suites

-include .env
DD_PORT ?= 8000
CG_API_PORT ?= 8100
CG_WEB_PORT ?= 5173
export DD_PORT CG_API_PORT CG_WEB_PORT

DD := doctor-dictation
DD_PY := $(DD)/.venv/bin
PYTHON ?= python3.12

.PHONY: setup dd-setup cg-setup dev dd cg test dd-test cg-test

setup: dd-setup cg-setup

dd-setup:
	cd $(DD) && $(PYTHON) -m venv .venv && .venv/bin/pip install -e ".[dev,pdf]"

cg-setup:
	$(MAKE) -C count-guard setup

dd:
	cd $(DD) && .venv/bin/uvicorn doctor_dictation.main:app --reload --port $(DD_PORT)

cg:
	$(MAKE) -C count-guard dev

dev:
	@echo "Doctor Dictation  http://127.0.0.1:$(DD_PORT)"
	@echo "Count Guard web   http://127.0.0.1:$(CG_WEB_PORT)  (API $(CG_API_PORT))"
	$(MAKE) -j2 dd cg

test: dd-test cg-test

dd-test:
	cd $(DD) && .venv/bin/pytest -q

cg-test:
	$(MAKE) -C count-guard test

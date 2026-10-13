# D0b: Container and Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Package the app as a Docker image behind a Caddy HTTPS proxy, prove it with a load test, and leave a go-live runbook that works on any Docker host with a domain.

**Architecture:** One image (Python 3.12 slim, package installed editable so `frontend/` stays beside it, headless Chromium, Noto fonts, ffmpeg, tini, non-root) plus a Caddy container; all state is the `data` volume. `tests/load/run_load.py` drives concurrent stub dictations and gates on 5xx, p95, PDFs actually written, and memory.

**Tech Stack:** Docker 29 + Compose, Caddy 2, Python 3.12, httpx, pytest. **Adds 10 tests** (4 functions, one parametrized; pure helpers of the load script, which is not collected). Run the suite first, note N, expect N+10 at the end.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` section 8, 7A.5; contract 4.8 in `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md`. Plan 15 of 15; all earlier plans applied, suite green.

## Assumptions about earlier plans
- B1a: `pyproject.toml` has an extra `pdf` pulling `playwright`; `pip install -e ".[pdf]"` works; `doctor_dictation.db.init_db` exists; entry point `doctor_dictation.main:app`. The install is **editable** because the app finds `frontend/` at `<package>/../frontend` (`FRONTEND_DIR`, `main.py:1056` before B1a).
- `DB_PATH` is honoured and PDFs go to `db_path().parent / "pdfs"` (`db/__init__.py:39-45`), so they land in `/data/pdfs`; B2b's template images are assumed to sit beside the DB (Task 1 step 1 checks).
- B2a uses Playwright's default `chromium.launch()`. Saves stay fail-soft (HTTP 200 even if the PDF fails), so the load test counts PDF files.
- Contract 4.1-4.3 env names (`ALLOW_STUB_PROVIDERS`, `STT_CHAIN=stub`, `LLM_PROVIDER=stub`, `STUB_*`, `DEMO_*`, `ALLOWED_ORIGINS`); D0a leaves `/health` open; `GET /api/v1/templates/active` is 200 once a template is accepted; `/api/transcribe` returns `{"transcript": ...}` (`main.py:540`).

## Global Constraints
- "Python 3.12 slim image, non-root user, Chromium and fonts installed (include Indian-language coverage), `WEB_CONCURRENCY` workers, volume mounted at `/data` with `DB_PATH=/data/app.db`, a reverse proxy providing HTTPS and a request-body limit, a container healthcheck on `/health`, and stub providers enabled only for the load test." (contract 4.8)
- Secrets live only in `.env.production`, created locally, never committed, never in the image; files here hold placeholders. Hosting is deliberately not chosen: nothing names a cloud provider.
- **No `git commit` or `git push`** (user rule): leave changes uncommitted, list files at the end. No new README: the runbook is Task 6 plus comments in the compose and Caddy files. Tests never touch the network.

## Review Focus
1. A failing PDF renderer must not pass the gate (saves return 200 regardless): the gate counts `.pdf` files (Task 3 test `pdfs_written`).
2. Chromium zombies pile up without an init (8,547 defunct processes after a few thousand saves in the trial): `tini`; Task 4 step 4 checks 0.
3. Two workers migrating a fresh volume at once fail with "database is locked" (seen in the trial): the CMD creates the DB first (Task 1 step 3).
4. Secrets must not reach the image or the log, and oversize uploads stop at the proxy with 413 while normal ones reach the app (Tasks 1, 2); data survives recreate and restores from backup (Task 6).

## File Structure
Create `Dockerfile`, `.dockerignore`, `docker-compose.yml`, `Caddyfile`, `.env.production.example`, `tests/load/{run_load.py,conftest.py}`, `tests/test_load_helpers.py`; modify nothing. All of it was run on 2026-10-13 (Docker 29.4.3, arm64) in a scratch copy with `backend/` renamed to `doctor_dictation/` plus a minimal `pyproject.toml`; the stubs and template routes did not exist, so a 10-line scratch shim stood in and the format path was the real rules fallback.

### Task 1: The image
**Files:** Create `Dockerfile`, `.dockerignore`.
**Interfaces:** Consumes package `doctor_dictation` (extra `pdf`) and `frontend/`. Produces image `doctor-dictation:local`, port `$PORT` (8000), uid 10001, state only under `/data`.
- [ ] **Step 1: Create `Dockerfile`.** First confirm `grep -n "pdf" pyproject.toml` shows the extra and `grep -n "def init_db" doctor_dictation/db/__init__.py` finds it; if B2b keeps template images outside `db_path().parent`, mount that directory under `/data` through its env var.
```dockerfile
FROM python:3.12-slim-bookworm
ENV XDG_CACHE_HOME=/tmp/.cache PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright DB_PATH=/data/app.db WEB_CONCURRENCY=2 PORT=8000

# Noto core covers the Indian scripts; ffmpeg is for ACC2 trimming; tini reaps Chromium's zombie children.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-noto-core fonts-noto-ui-core fontconfig ffmpeg tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Dependency layer first, so code edits do not reinstall Chromium.
COPY pyproject.toml ./
RUN mkdir doctor_dictation && touch doctor_dictation/__init__.py \
 && pip install -e ".[pdf]" \
 && playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/* && fc-cache -f && chmod -R a+rX /ms-playwright

# Editable install on purpose: the app finds frontend/ at <package>/../frontend, so keep the repo layout.
COPY doctor_dictation ./doctor_dictation
COPY frontend ./frontend

RUN useradd --system --uid 10001 --home-dir /app app && mkdir -p /data && chown app:app /data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=4)"
# Create the database once before the workers start: two workers migrating a fresh volume at the same
# moment fail with "database is locked". uvicorn reads WEB_CONCURRENCY as its default --workers.
ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "python -c 'from doctor_dictation.db import init_db; init_db()' && exec uvicorn doctor_dictation.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
```
- [ ] **Step 2: Create `.dockerignore`**
```
.git
.venv*
.env
.env.*
!.env.production.example
**/secrets.json
**/__pycache__
.superpowers
tests
docs
*.md
doctor_dictation/data
doctor_dictation/stt_models
```
- [ ] **Step 3: Build and start** (first build about 4 minutes, Chromium download). Four workers on a fresh volume is the migration-race check:
```bash
docker build -t doctor-dictation:local . && docker run -d --name d0b-try -e WEB_CONCURRENCY=4 -v d0b-try-data:/data -p 18000:8000 doctor-dictation:local
sleep 15; curl -s -o /dev/null -w "%{http_code}\n" localhost:18000/health; docker ps --format '{{.Status}}'
```
Expected: `200` and `Up ... (healthy)`.
- [ ] **Step 4: Prove the container properties**
```bash
docker exec d0b-try id -u                                  # 10001
docker images doctor-dictation:local --format '{{.Size}}'   # about 1.6GB (2.2GB with full chromium instead of --only-shell)
docker exec d0b-try sh -c 'ls -A /app | grep -c "^\.env"'; docker inspect doctor-dictation:local --format '{{.Config.Env}}' | grep -ciE "api_key|password"   # 0, 0
docker exec -i d0b-try python - <<'PY'
import pathlib
from doctor_dictation.pdf import render_pdf
b = pathlib.Path(render_pdf("<p style='font-size:24px'>हिन्दी रोगी / తెలుగు రోగి</p>", "/data/pdfs/probe.pdf")).read_bytes()
print(b[:5], len(b), b"Telugu" in b)
PY
```
Expected last line: `b'%PDF-'`, 13,000-19,000 bytes, `True`. To see glyphs: `docker cp d0b-try:/data/pdfs/probe.pdf .`, `pdftoppm -png -r 90 probe.pdf probe`, and check both scripts show letters, not boxes (trial: FreeSans and Noto Sans Telugu). Then `docker rm -f d0b-try; docker volume rm d0b-try-data`. Leave uncommitted.

### Task 2: Compose stack, Caddy proxy, production env template
**Files:** Create `docker-compose.yml`, `Caddyfile`, `.env.production.example`.
**Interfaces:** Consumes the image. Produces services `app` (loopback `${APP_LOCAL_PORT:-8000}`) and `caddy` (80/443), volume `doctor-dictation_data`, selectors `APP_ENV_FILE` (Task 4) and `APP_TAG` (rollback).
- [ ] **Step 1: Create `docker-compose.yml`**
```yaml
# Demo deployment: app + Caddy on any Docker host with a domain; ports 80 and 443 must be public.
# Runbook = the D0b plan, Task 6. Always pass the env file:
#   docker compose --env-file .env.production up -d --build | ps | logs -f app caddy
name: doctor-dictation            # fixes the volume name: doctor-dictation_data
services:
  app:
    build: .
    image: doctor-dictation:${APP_TAG:-local}
    env_file: ${APP_ENV_FILE:-.env.production}
    environment:
      DB_PATH: /data/app.db          # PDFs and template images live beside it, under /data
    volumes:
      - data:/data                   # the only state; back it up
    ports:
      - "127.0.0.1:${APP_LOCAL_PORT:-8000}:8000"   # loopback only: local checks and the load test
    restart: unless-stopped
    # mem_limit: 2g    # uncomment on a small host so Chromium cannot starve it
  caddy:
    image: caddy:2
    environment:
      SITE_ADDRESS: ${SITE_ADDRESS:?set SITE_ADDRESS in the env file}
      UPLOAD_LIMIT: ${UPLOAD_LIMIT:-11MiB}
    ports: ["80:80", "443:443", "443:443/udp"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data             # certificates; losing it means re-issuing them
      - caddy_config:/config
    depends_on:
      app:
        condition: service_healthy
    restart: unless-stopped
volumes:
  data:
  caddy_data:
  caddy_config:
```
- [ ] **Step 2: Create `Caddyfile`**
```
# HTTPS reverse proxy. SITE_ADDRESS comes from the env file; "localhost" gives a local self-signed cert.
{$SITE_ADDRESS} {
	encode zstd gzip
	log {
		output stdout
		format filter {
			wrap json
			fields {
				request>headers>Authorization delete
				request>headers>Cookie delete
			}
		}
	}
	# Limit sits just above MAX_AUDIO_BYTES (10 MiB) and TEMPLATE_MAX_IMAGE_BYTES (8 MiB), so the
	# app explains the normal "too large" case. Raise UPLOAD_LIMIT if you raise either setting.
	@uploads path /api/transcribe /api/v1/templates
	request_body @uploads {
		max_size {$UPLOAD_LIMIT:11MiB}
	}
	@json not path /api/transcribe /api/v1/templates
	request_body @json {
		max_size 1MiB
	}
	reverse_proxy app:8000 {
		# /api/format may wait 60 s for the LLM; the proxy gives up at 90 s.
		transport http {
			dial_timeout 5s
			response_header_timeout 90s
		}
	}
}
```
- [ ] **Step 3: Create `.env.production.example`**
```
# Copy to .env.production and edit. Never commit it (.gitignore blocks .env.*). Change every REPLACE_ME.
SITE_ADDRESS=demo.example.com
ALLOWED_ORIGINS=https://demo.example.com
DEMO_MODE=1
DEMO_USERNAME=demo
DEMO_PASSWORD=REPLACE_ME_generated_password
LLM_PROVIDER=openai
LLM_MODEL=gpt-6-luna
LLM_VISION_MODEL=
OPENAI_API_KEY=REPLACE_ME_your_openai_key
STT_ENGINE=auto
ALLOW_STUB_PROVIDERS=0
MAX_AUDIO_BYTES=10485760
TEMPLATE_MAX_IMAGE_BYTES=8388608
TEMPLATE_UPLOADS_PER_DAY=10
UPLOAD_LIMIT=11MiB
STT_USE_HINTS=0
STT_TRIM_SILENCE=0
WEB_CONCURRENCY=2   # one per CPU core; each worker runs its own Chromium (about 300 MiB)
```
- [ ] **Step 4: Validate and rehearse** (`localhost` gives a self-signed certificate, hence `-k`):
```bash
cp .env.production.example .env.production && sed -i.bak 's/demo.example.com/localhost/g' .env.production && rm .env.production.bak
docker compose --env-file .env.production config -q && echo compose-ok
docker run --rm -v "$PWD/Caddyfile:/etc/caddy/Caddyfile:ro" -e SITE_ADDRESS=localhost caddy:2 caddy validate --config /etc/caddy/Caddyfile 2>&1 | tail -1
docker compose --env-file .env.production up -d --build && sleep 20 && docker compose --env-file .env.production ps
```
Expected: `compose-ok`, `Valid configuration`, `app` healthy. If port 80, 443 or 8000 is busy, free it or set `APP_LOCAL_PORT=18000`.
- [ ] **Step 5: Prove the proxy rules**
```bash
head -c 12000000 /dev/zero > /tmp/big.bin; head -c 2000000 /dev/zero > /tmp/mid.bin
curl -sk -o /dev/null -w "health %{http_code}\n" https://localhost/health                                      # 200
curl -sk -o /dev/null -w "12MB audio %{http_code}\n" -F audio=@/tmp/big.bin https://localhost/api/transcribe   # 413 from Caddy
curl -sk -o /dev/null -w "2MB audio %{http_code}\n" -F audio=@/tmp/mid.bin https://localhost/api/transcribe     # not 413: the app answers
curl -sk -o /dev/null -w "2MB json %{http_code}\n" -H 'content-type: application/json' --data-binary @/tmp/mid.bin https://localhost/api/format   # 413
curl -sk -u demo:SECRET-CHECK -o /dev/null https://localhost/health
docker compose --env-file .env.production logs caddy | grep -ci authorization                                  # 0
docker compose --env-file .env.production down; rm /tmp/big.bin /tmp/mid.bin
```
Trial: 200, 413, 502 (the app answered; no STT configured), 413, 0. Leave uncommitted.

### Task 3: Load-test script and its helper tests
**Files:** Create `tests/test_load_helpers.py`, `tests/load/conftest.py`, `tests/load/run_load.py`.
**Interfaces:** Produces `percentile(values, p)`, `parse_mem_mib(text)`, `memory_growth(samples) -> (mib, relative)`, `evaluate_gate(...) -> list[str]`, `P95_LIMIT_S = 6.0`; exit codes 0 pass, 1 gate failed, 2 setup error. **Not collected by pytest:** the file is not named `test_*.py`, plus the conftest guard.
**The gate (fixed before the run, spec 8.4):** zero 5xx and zero failed requests; one doctor's whole dictation (transcribe, format, save) p95 at most **6.0 s**; one PDF per save; the memory floor of the last third grows under 10 percent or 50 MiB. Why 6.0 s: with 8 concurrent doctors on a 2-CPU, 2 GB container (the smallest target host) the trial's save p95 was 3.2 s with today's Chromium-per-save renderer (0.5 s on 12 cores); two stub delays of 0.3 s bring that to about 3.8 s, so 6.0 s leaves 1.5x room. Lower the limit if Task 4 shows B2a's pooled renderer far below it; never raise it without a written reason in the final report.
- [ ] **Step 1: Write the failing tests** — `tests/test_load_helpers.py`:
```python
"""Pure helpers of the load-test script (the script itself needs a running container)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "load"))
import run_load as L  # noqa: E402


def test_percentile_nearest_rank():
    data = [float(n) for n in range(1, 101)]
    assert (L.percentile(data, 50), L.percentile(data, 95)) == (50.0, 95.0)
    assert (L.percentile([], 95), L.percentile([7.0], 95)) == (0.0, 7.0)


def test_parse_mem_mib():
    assert (L.parse_mem_mib("512MiB / 7.7GiB"), L.parse_mem_mib("1.5GiB / 7GiB")) == (512.0, 1536.0)
    with pytest.raises(ValueError):
        L.parse_mem_mib("n/a")


def test_memory_growth_ignores_spikes_but_sees_a_rising_floor():
    assert L.memory_growth([400, 1500, 420, 1400, 410, 1600, 405, 1500, 415, 1450, 400, 1550])[0] <= 15
    grown, rel = L.memory_growth([400] * 8 + [450, 500, 700, 800])
    assert grown >= 200 and rel > 0.4


def _gate(**over):
    base = dict(total=100, status_5xx=0, other_failures=0, dictation_p95=2.0, saves=50,
                pdfs_written=50, mem_samples=[500.0] * 12)
    return L.evaluate_gate(**{**base, **over})


@pytest.mark.parametrize("over,word", [
    ({"status_5xx": 1}, "5xx"), ({"other_failures": 2}, "failed"), ({"total": 0}, "no requests"),
    ({"dictation_p95": L.P95_LIMIT_S + 0.1}, "p95"), ({"pdfs_written": 49}, "PDFs"),
    ({"mem_samples": [500.0]}, "memory samples"), ({"mem_samples": [400.0] * 10 + [900.0] * 2}, "memory grew"),
])
def test_gate_passes_a_healthy_run_and_fails_on_each_condition(over, word):
    assert _gate() == []
    assert any(word in p for p in _gate(**over))
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_load_helpers.py -q`. Expected: `ModuleNotFoundError: No module named 'run_load'`.
- [ ] **Step 3: Create `tests/load/conftest.py`** with exactly `collect_ignore_glob = ["*.py"]` (a second guard beside the file name).
- [ ] **Step 4: Create `tests/load/run_load.py`**
```python
"""Load test for the demo container (D0b); not collected by pytest. Run on the Docker host:
  python tests/load/run_load.py --url http://127.0.0.1:8000 --container doctor-dictation-app-1 --user demo --password ...
Exit 0 = gate passed, 1 = failed, 2 = setup error. Needs the stub providers and an active template."""
import argparse
import asyncio
import math
import subprocess
import sys
import time

import httpx

P95_LIMIT_S = 6.0          # one doctor's whole dictation, seconds (justified in the plan)
MEM_GROWTH_LIMIT, MEM_SLACK_MIB = 0.10, 50.0   # last-third floor growth: relative, and above this many MiB


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(max(1, math.ceil(p / 100 * len(ordered))), len(ordered)) - 1] if ordered else 0.0


def parse_mem_mib(text):
    """'123.4MiB / 7.7GiB' (docker stats) -> 123.4"""
    used = text.split("/")[0].strip()
    for unit, factor in (("GiB", 1024.0), ("MiB", 1.0)):
        if used.endswith(unit):
            return float(used[: -len(unit)]) * factor
    raise ValueError(f"unrecognised memory value: {text!r}")


def memory_growth(samples):
    """(MiB, relative) growth in the last third: floor (min) of its 2nd half vs its 1st half.
    Chromium launches spike usage, so max and median are noise; a leak raises the floor."""
    last = samples[(2 * len(samples)) // 3:]
    if len(last) < 4:
        return 0.0, 0.0
    before, after = min(last[: len(last) // 2]), min(last[len(last) // 2:])
    return after - before, (after - before) / before if before else 0.0


def evaluate_gate(*, total, status_5xx, other_failures, dictation_p95, saves, pdfs_written, mem_samples):
    """Failed-gate messages; an empty list means pass."""
    bad = []
    if total == 0:
        bad.append("no requests were made")
    if status_5xx:
        bad.append(f"{status_5xx} responses were 5xx (limit 0)")
    if other_failures:
        bad.append(f"{other_failures} requests failed (non-2xx or network error)")
    if dictation_p95 > P95_LIMIT_S:
        bad.append(f"dictation p95 {dictation_p95:.2f}s exceeds {P95_LIMIT_S:.1f}s")
    if pdfs_written < saves:
        bad.append(f"only {pdfs_written} PDFs on disk for {saves} saves (renderer failing soft?)")
    if len(mem_samples) < 6:
        bad.append("fewer than 6 memory samples: run longer or check --container")
    else:
        grown, rel = memory_growth(mem_samples)
        if grown > MEM_SLACK_MIB and rel > MEM_GROWTH_LIMIT:
            bad.append(f"memory grew {grown:.0f} MiB ({rel:.0%}) across the last third")
    return bad


def docker_out(*args):
    done = subprocess.run(["docker", *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


async def sample_memory(container, samples, stop):
    while not stop.is_set():
        text = await asyncio.to_thread(docker_out, "stats", "--no-stream", "--format", "{{.MemUsage}}", container)
        if text:
            samples.append(parse_mem_mib(text))
        await asyncio.sleep(0.5)


async def post(client, path, stats, **kw):
    stats["requests"] += 1
    try:
        resp = await client.post(path, **kw)
    except httpx.HTTPError as exc:
        stats["failures"] += 1
        print(f"  {path}: {type(exc).__name__}", file=sys.stderr)
        return None
    stats["5xx"] += resp.status_code >= 500
    if resp.status_code >= 300:
        stats["failures"] += 1
        print(f"  {path}: HTTP {resp.status_code} {resp.text[:100]}", file=sys.stderr)
        return None
    return resp.json()


async def dictation(client, n, stats):
    started = time.perf_counter()
    audio = {"audio": ("load.webm", b"\x1aE\xdf\xa3load-test", "audio/webm")}
    heard = await post(client, "/api/transcribe", stats, files=audio)
    text = heard and f"{heard['transcript']} Visit {n}."  # unique text defeats the format cache
    done = text and await post(client, "/api/format", stats, json={"transcript": text})
    if not done:
        return
    form = {**done["structured"], "patientName": f"Load Patient {n}", "opNo": f"LOAD-{n}"}
    saved = await post(client, "/api/v1/documents", stats, json={
        "structured": form, "confirmed_rows": list(range(len(form.get("rx") or []))),
        "engine": done.get("engine", ""), "transcript_sha256": done.get("transcript_sha256", "")})
    if saved:
        stats["saves"] += 1
        stats["durations"].append(time.perf_counter() - started)


async def run(args):
    samples, stop = [], asyncio.Event()
    stats = {"requests": 0, "failures": 0, "5xx": 0, "saves": 0, "durations": []}
    auth = (args.user, args.password) if args.user else None
    async with httpx.AsyncClient(base_url=args.url.rstrip("/"), auth=auth, timeout=120.0,
                                 limits=httpx.Limits(max_connections=args.concurrency * 2)) as client:
        try:
            up = (await client.get("/health")).status_code == 200
            templated = (await client.get("/api/v1/templates/active")).status_code == 200
        except httpx.HTTPError:
            up = templated = False
        if not (up and templated):
            return print("setup: server down, or no active template (accept one first)", file=sys.stderr) or 2
        pdf_cmd = ("exec", args.container, "sh", "-c", "find /data/pdfs -name '*.pdf' | wc -l")
        pdfs_before = int(docker_out(*pdf_cmd) or 0)
        sampler = asyncio.create_task(sample_memory(args.container, samples, stop))

        async def doctor(idx):
            for k in range(args.dictations):
                await dictation(client, idx * 100000 + k, stats)

        await asyncio.gather(*(doctor(i) for i in range(args.concurrency)))
        stop.set()
        await sampler
    pdfs, d = int(docker_out(*pdf_cmd) or 0) - pdfs_before, stats["durations"]
    print(f"requests={stats['requests']} 5xx={stats['5xx']} failures={stats['failures']}")
    print(f"dictation p50={percentile(d, 50):.2f}s p95={percentile(d, 95):.2f}s max={max(d, default=0):.2f}s; "
          f"memory peak={max(samples, default=0):.0f} MiB; pdfs written: {pdfs} for {stats['saves']} saves")
    problems = evaluate_gate(total=stats["requests"], status_5xx=stats["5xx"], other_failures=stats["failures"],
                             dictation_p95=percentile(d, 95), saves=stats["saves"], pdfs_written=pdfs,
                             mem_samples=samples)
    print("\n".join(f"GATE FAIL: {p}" for p in problems) or "GATE PASS")
    return 1 if problems else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", required=True)
    ap.add_argument("--container", required=True)
    ap.add_argument("--user", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--dictations", type=int, default=100)
    sys.exit(asyncio.run(run(ap.parse_args())))
```
- [ ] **Step 5: Run** `.venv/bin/python -m pytest tests/test_load_helpers.py -q` (expect `10 passed`), then `.venv/bin/python -m pytest tests/load --collect-only -q | tail -1` (expect no tests collected). Leave uncommitted.

### Task 4: Run the load gate against the real stack
**Files:** none in the repo (the `.env.*` files below are local and git-ignored).
**Interfaces:** Consumes Tasks 1-3, the stub providers, D0a auth, B2b templates. Produces the p95 and memory numbers for the final report.
One `STUB_LLM_JSON` cannot be both a layout and a prescription, so phase A accepts a template with a layout stub, phase B restarts with a prescription stub (the volume, hence the template, survives).
- [ ] **Step 1: Create the throwaway env files** (throwaway password, local only):
```bash
cp .env.production.example .env.loadtest
sed -i.bak 's/demo.example.com/localhost/g; s/^DEMO_PASSWORD=.*/DEMO_PASSWORD=loadtest-only/; s/^LLM_PROVIDER=.*/LLM_PROVIDER=stub/; s/^ALLOW_STUB_PROVIDERS=.*/ALLOW_STUB_PROVIDERS=1/' .env.loadtest && rm .env.loadtest.bak
printf '%s\n' 'STT_CHAIN=stub' 'STUB_DELAY_MS=300' "STUB_TRANSCRIPT=patient name is Load Patient, 40 year old male, tablet paracetamol 500 mg twice a day for 3 days." >> .env.loadtest
cp .env.loadtest .env.lt-layout; cp .env.loadtest .env.lt-rx
echo "STUB_LLM_JSON='{\"header\":[{\"type\":\"text\",\"field\":\"clinic_name\",\"role\":\"title\",\"align\":\"center\"},{\"type\":\"rule\",\"color\":\"#1a3c6e\",\"thickness\":\"thin\"}],\"footer\":[{\"type\":\"text\",\"field\":\"address\",\"role\":\"small\",\"align\":\"center\"}],\"body\":{\"top\":0.2,\"bottom\":0.92},\"profile\":{\"doctor_name\":\"Dr Load\",\"qualifications\":\"MBBS\",\"reg_no\":\"R1\",\"clinic_name\":\"Load Clinic\",\"address\":\"1 Test Road\",\"phone\":\"000\"}}'" >> .env.lt-layout
echo "STUB_LLM_JSON='{\"patientName\":\"\",\"ageSex\":\"\",\"opNo\":\"\",\"diagnosis\":[\"Fever\"],\"complaints\":[\"Fever\"],\"investigations\":[],\"rx\":[{\"form\":\"Tab.\",\"name\":\"Paracetamol\",\"strength\":\"500 mg\",\"dose\":\"1-0-1\",\"timing\":\"After food\",\"duration\":\"3 days\",\"instructions\":\"\"}],\"advice\":[],\"review\":\"\"}'" >> .env.lt-rx
```
- [ ] **Step 2: Phase A, accept a template**
```bash
export APP_LOCAL_PORT=18000 U=demo:loadtest-only B=http://127.0.0.1:18000
APP_ENV_FILE=.env.lt-layout docker compose --env-file .env.lt-layout up -d --build && sleep 20
.venv/bin/python -c "from PIL import Image; Image.new('RGB',(1240,1754),'white').save('/tmp/pad.png')"
ID=$(curl -s -u $U -F image=@/tmp/pad.png $B/api/v1/templates | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
curl -s -o /dev/null -w "accept %{http_code}\n" -u $U -X POST $B/api/v1/templates/$ID/accept
```
Expected: `accept 200`. On failure read `docker compose --env-file .env.lt-layout logs app | tail` and fix the layout JSON against `validate_layout` (B2a).
- [ ] **Step 3: Phase B, run the gate**
```bash
APP_ENV_FILE=.env.lt-rx docker compose --env-file .env.lt-rx up -d app && sleep 15
.venv/bin/python tests/load/run_load.py --url $B --container doctor-dictation-app-1 --user demo --password loadtest-only \
  --concurrency 8 --dictations 100; echo "exit=$?"
```
Expected: `requests=2400 5xx=0 failures=0`, `dictation p95` under 6.0 s, `pdfs written: 800 for 800 saves`, `GATE PASS`, `exit=0` (emulated trial: p95 0.72 s, peak 1,253 MiB, 480 of 480 PDFs). Run again with `--concurrency 16` to see headroom.
- [ ] **Step 4: Zombie check, then tear down**
```bash
docker compose --env-file .env.lt-rx exec -T app sh -c 'z=0; for d in /proc/[0-9]*; do grep -q "^State:.Z" $d/status 2>/dev/null && z=$((z+1)); done; echo zombies=$z'   # 0
docker compose --env-file .env.lt-rx down -v; rm -f .env.loadtest .env.lt-layout .env.lt-rx /tmp/pad.png
```
If the gate fails for a real reason, fix the cause; never edit thresholds to pass. Leave uncommitted.

### Task 5: Final verification
- [ ] **Step 1:** `.venv/bin/python -m pytest tests/ -q` gives N+10 passed. Then `.venv/bin/uvicorn doctor_dictation.main:app --port 8001`; `curl -s localhost:8001/health` shows `"ok":true`; stop it.
- [ ] **Step 2:** `git status --short` lists only the eight files in File Structure and not `.env.production`; `grep -rn "sk-" Dockerfile docker-compose.yml Caddyfile .env.production.example` prints nothing.
- [ ] **Step 3:** Report files, test count, measured p95, peak memory, image size, and what was not verified (a real certificate needs a public domain; real OpenAI calls; any Assumption an earlier plan broke).

### Task 6: Demo go-live runbook
The hosting platform is **not chosen**: any Linux host with Docker Engine 24+ (Compose plugin), a public IP, ports 80/443 open and a domain works. Run from the repo root on that host.
- [ ] **Step 1: Owner decides first:** (a) host (2 vCPU and 2 GB minimum, 4 GB comfortable); (b) domain and who can add its A record; (c) who receives the demo username and password, and over which channel; (d) which OpenAI key and spending limit; (e) whether the LLM accepts images, else set `LLM_VISION_MODEL`.
- [ ] **Step 2: DNS, firewall, code.** A record `demo.<yourdomain>` to the host IP (`dig +short demo.<yourdomain>` prints it); open TCP 80, 443 and UDP 443. Then `git clone <repo-url> doctor-dictation && cd doctor-dictation`; `ls -a | grep '^\.env'` shows only the example files.
- [ ] **Step 3: Password and env file.** `python3 -c "import secrets; print(secrets.token_urlsafe(18))"` (the app compares the plain value in constant time; no hash exists); keep it in a password manager. `cp .env.production.example .env.production && chmod 600 .env.production`, then edit `SITE_ADDRESS`, `ALLOWED_ORIGINS` (`https://` plus the domain), `DEMO_USERNAME`, `DEMO_PASSWORD`, `OPENAI_API_KEY`. `grep -c REPLACE_ME .env.production` must print 0; `git check-ignore .env.production` must print the path.
- [ ] **Step 4: Start:** `docker compose --env-file .env.production up -d --build`; repeat `docker compose --env-file .env.production ps` until `app` is `healthy`; `docker compose --env-file .env.production logs caddy | grep -i "certificate obtained"` confirms HTTPS.
- [ ] **Step 5: First-login check**
```bash
D=https://demo.<yourdomain>
curl -s -o /dev/null -w "no login %{http_code}\n" $D/api/v1/profile                      # 401
curl -s -o /dev/null -w "health   %{http_code}\n" $D/health                               # 200
curl -s -u "<user>:<password>" $D/api/health | grep -o '"demo":[a-z]*'        # "demo":true
```
In a browser: sign in, see the "Demo, fake patients only" banner, press the mic (allowed because of HTTPS), dictate one fake patient, save, open the PDF.
- [ ] **Step 6: Template smoke.** Upload a photo of a blank pad in the letterhead panel, check the preview, accept. "No vision-capable model" means set `LLM_VISION_MODEL`, then `docker compose --env-file .env.production up -d app`. Save another fake prescription; `docker compose --env-file .env.production exec app ls -l /data/pdfs` shows a new file.
- [ ] **Step 7: Back up** (app stopped for a clean SQLite copy, about 10 s):
```bash
docker compose --env-file .env.production stop app
docker run --rm -v doctor-dictation_data:/data -v "$PWD":/backup alpine tar czf /backup/data-$(date +%F).tgz -C /data .
docker compose --env-file .env.production start app
mkdir -p /tmp/rt && tar xzf data-$(date +%F).tgz -C /tmp/rt && docker run --rm -v /tmp/rt:/data --entrypoint python doctor-dictation:local -c "import sqlite3; print(sqlite3.connect('/data/app.db').execute('select count(*) from documents').fetchone())"
```
The last command proves the backup opens; copy the `.tgz` off the host. Restore: stop app, `docker run --rm -v doctor-dictation_data:/data -v "$PWD":/backup alpine sh -c "rm -rf /data/* && tar xzf /backup/data-<date>.tgz -C /data"`, start app.
- [ ] **Step 8: Update or roll back.** Update: back up (step 7), `docker tag doctor-dictation:local doctor-dictation:prev`, `git pull && docker compose --env-file .env.production up -d --build`, repeat step 5. Roll back: `APP_TAG=prev docker compose --env-file .env.production up -d --no-build app`; if the new version applied a database migration, also restore the step-7 backup (migrations only go forward); repeat step 5.
- [ ] **Step 9: Rotate or stop.** New password: edit `DEMO_PASSWORD`, `docker compose --env-file .env.production up -d app`. Offline, data kept: `docker compose --env-file .env.production stop caddy app`. Remove everything including data (irreversible, back up first): `docker compose --env-file .env.production down -v`.

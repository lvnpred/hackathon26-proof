# Doctor Dictation image: Python 3.12, headless Chromium (PDF), Indian-script fonts, tini, non-root.
# Builds with Docker or Podman. All state lives under /data (the volume): directory.db, clinics/<slug>/.
FROM python:3.12-slim-bookworm
ENV XDG_CACHE_HOME=/tmp/.cache PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright MULTI_CLINIC=1 DATA_DIR=/data WEB_CONCURRENCY=2 PORT=8000
# The clinic zone: the visit day and the printed date follow it, not the host clock (code reads TZ; see api/visit.py).
ENV TZ=Asia/Kolkata

# tzdata: zone data for TZ (the slim base may not ship it). Noto core covers the Indian scripts; ffmpeg is for optional audio trimming; tini reaps Chromium's zombie children.
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-noto-core fonts-noto-ui-core fontconfig ffmpeg tini tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
# Dependency layer first, so code edits do not reinstall Chromium.
COPY doctor_dictation/requirements.txt doctor_dictation/requirements-pdf.txt ./reqs/
RUN pip install -r reqs/requirements.txt -r reqs/requirements-pdf.txt \
 && playwright install --with-deps --only-shell chromium \
 && rm -rf /var/lib/apt/lists/* && fc-cache -f && chmod -R a+rX /ms-playwright

# Editable install on purpose: the app finds frontend/ at <package>/../frontend, so keep the repo layout.
COPY pyproject.toml README.md ./
COPY doctor_dictation ./doctor_dictation
COPY frontend ./frontend
RUN pip install --no-deps -e .

RUN useradd --system --uid 10001 --home-dir /app app && mkdir -p /data && chown app:app /data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ['PORT'], timeout=4)"
# Migrate every clinic once before the workers start: several workers migrating a fresh volume at the same
# moment fail with "database is locked". uvicorn reads WEB_CONCURRENCY as its default --workers.
# --forwarded-allow-ips='*' is safe only because the app port is never exposed beyond the proxy and loopback (compose).
ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "python -m doctor_dictation.admin migrate-all && exec uvicorn doctor_dictation.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]

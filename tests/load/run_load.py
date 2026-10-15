"""Load test for the container stack (D0b); not collected by pytest. Run on the host:
  python tests/load/run_load.py --url http://127.0.0.1:8000 --container doctor-dictation-app-1 \
      --user dr.load --password <temporary password> --new-password <permanent password>
Exit 0 = gate passed, 1 = failed, 2 = setup error. The server needs the stub providers (ALLOW_STUB_PROVIDERS=1,
STT_CHAIN=stub, LLM_PROVIDER=stub, STUB_LLM_JSON = a prescription) and a clinic with that user."""
import argparse
import asyncio
import math
import shutil
import subprocess
import sys
import time

import httpx

P95_LIMIT_S = 6.0          # one doctor's whole dictation, seconds (justified in the plan)
MEM_GROWTH_LIMIT, MEM_SLACK_MIB = 0.10, 50.0   # last-third floor growth: relative, and above this many MiB
UNITS = (("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10), ("GB", 1e9), ("MB", 1e6), ("kB", 1e3), ("B", 1.0))
CLIENT = {"X-DD-Client": "1"}     # the app's CSRF header on every unsafe request


def percentile(values, p):
    ordered = sorted(values)
    return ordered[min(max(1, math.ceil(p / 100 * len(ordered))), len(ordered)) - 1] if ordered else 0.0


def parse_mem_mib(text):
    """'123.4MiB / 7.7GiB' (docker stats) or '123.4MB / 4.1GB' (podman stats) -> MiB used"""
    used = text.split("/")[0].strip()
    for unit, factor in UNITS:
        if used.endswith(unit):
            return float(used[: -len(unit)]) * factor / 2**20
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


ENGINE = "podman" if shutil.which("podman") else "docker"


def engine_out(*args):
    done = subprocess.run([ENGINE, *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


async def sample_memory(container, samples, stop):
    while not stop.is_set():
        text = await asyncio.to_thread(engine_out, "stats", "--no-stream", "--format", "{{.MemUsage}}", container)
        if text:
            samples.append(parse_mem_mib(text))
        await asyncio.sleep(0.5)


async def post(client, path, stats, **kw):
    stats["requests"] += 1
    try:
        resp = await client.post(path, headers=CLIENT, **kw)
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
        "structured": form, "confirmed_rows": list(range(len(form.get("rx") or [])))})
    if saved:
        stats["saves"] += 1
        stats["durations"].append(time.perf_counter() - started)


async def sign_in(client, args):
    """One session cookie shared by every simulated doctor. A temporary password is changed once."""
    resp = await client.post("/api/v1/auth/login", headers=CLIENT, json={"username": args.user, "password": args.password})
    if resp.status_code != 200:
        return f"sign-in refused (HTTP {resp.status_code}): check --user and --password"
    if resp.json().get("must_change_password"):
        if not args.new_password:
            return "the password is temporary: pass --new-password (the test sets it)"
        resp = await client.post("/api/v1/auth/change-password", headers=CLIENT,
                                 json={"current_password": args.password, "new_password": args.new_password})
        if resp.status_code != 200:
            return f"change-password refused (HTTP {resp.status_code}): {resp.text[:100]}"
    return ""


async def run(args):
    samples, stop = [], asyncio.Event()
    stats = {"requests": 0, "failures": 0, "5xx": 0, "saves": 0, "durations": []}
    async with httpx.AsyncClient(base_url=args.url.rstrip("/"), timeout=120.0, verify=not args.insecure,
                                 limits=httpx.Limits(max_connections=args.concurrency * 2)) as client:
        try:
            up = (await client.get("/health")).status_code == 200
            problem = await sign_in(client, args) if up else "server down"
        except httpx.HTTPError as exc:
            problem = f"cannot reach the server: {type(exc).__name__}"
        if problem:
            return print(f"setup: {problem}", file=sys.stderr) or 2
        pdf_cmd = ("exec", args.container, "sh", "-c", "find /data -name '*.pdf' | wc -l")
        pdfs_before = int(engine_out(*pdf_cmd) or 0)
        sampler = asyncio.create_task(sample_memory(args.container, samples, stop))

        async def doctor(idx):
            for k in range(args.dictations):
                await dictation(client, idx * 100000 + k, stats)

        await asyncio.gather(*(doctor(i) for i in range(args.concurrency)))
        stop.set()
        await sampler
    pdfs, d = int(engine_out(*pdf_cmd) or 0) - pdfs_before, stats["durations"]
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
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--new-password", default="", help="permanent password to set when the first one is temporary")
    ap.add_argument("--insecure", action="store_true", help="accept a self-signed certificate (https://localhost)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--dictations", type=int, default=100)
    sys.exit(asyncio.run(run(ap.parse_args())))

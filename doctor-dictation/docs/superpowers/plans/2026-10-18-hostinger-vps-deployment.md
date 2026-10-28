# Hostinger VPS deployment plan

**Status (2026-10-18):** executed. Deployed on a Hostinger KVM 2 at `gsr.lightday.online`; Phases 1, 2 and the backup part of Phase 4 are done, Phase 3 (smoke test) and the rest of Phase 4/5 are open. See `docs/working/2026-10-18-deployment/README.md`. Extends `docs/deploy/runbook.md` (the app + Caddy compose stack already exists: `docker-compose.yml`, `Caddyfile`, `.env.production.example`).

## Summary (read this first)

- **Recommendation:** Hostinger **KVM 2** (2 vCPU, 8 GB RAM, NVMe), a plain **Ubuntu 24.04** image, Docker + the existing compose stack, in the **India (Mumbai) data centre if the plan offers it**. Verify current plan names, specs and prices on Hostinger's site before buying; they change.
- **Why KVM 2:** the app is light (FastAPI + SQLite). Speech-to-text and the LLM are cloud calls (`.env.production.example`: `STT_ENGINE=auto`, `OPENAI_API_KEY`). The real memory cost is headless Chromium for PDFs, about 300 MiB per worker (`.env.production.example`, `WEB_CONCURRENCY=2`), plus the optional local Whisper fallback. KVM 1 (1 vCPU) is too tight for two workers plus that fallback. KVM 4 is not needed until roughly ten busy clinics.
- **The one decision that is not technical:** real patient data. The letterhead screen still says "this demo must only ever see fake data", and dictated text and audio go to OpenAI (outside India). Going live with real patients needs your consent text, retention rule, breach process and an explicit yes to the cloud providers (India DPDP Act 2023 applies). The plan below has a gate for it (Phase 0).
- **Biggest gap in the repo:** backups are manual and need the app stopped (`docs/deploy/runbook.md` step 4). Phase 4 adds an automatic nightly backup copied off the server.

## Plan choice

| Option | Spec (verify) | Fits? | Verdict |
|---|---|---|---|
| KVM 1 | 1 vCPU, 4 GB | One worker only; local Whisper fallback would starve it | Pilot with one clinic only |
| **KVM 2** | 2 vCPU, 8 GB | Two workers + Chromium + caddy, headroom for the fallback | **Choose** |
| KVM 4 | 4 vCPU, 16 GB | Four workers, many clinics | Upgrade later (VPS resize keeps data) |
| Shared / cloud hosting | n/a | Needs Docker, long-running Chromium, root | No |

Non-hardware choices: pick the 12 or 24 month term only after the 2-week pilot; enable Hostinger's snapshot/backup add-on if offered, but treat it as a second copy, not the main backup.

## Phases

### Phase 0 — Decisions before any server (you)
1. Domain name and who controls its DNS (an `A` record to the VPS IP is needed for HTTPS).
2. Real patient data: yes/no, and for whom first. If yes: written consent wording, retention period, who is told after a breach, and acceptance that audio and text go to OpenAI. If "not yet": run the pilot on fake data only.
3. Data centre location (India preferred for latency and data-residency comfort).
4. Where off-site backups go (a second provider bucket, e.g. any S3-compatible store, or your own machine).

### Phase 1 — Provision and harden (about 1 hour)
1. Buy KVM 2, Ubuntu 24.04, add your SSH key at creation. Do not use a password.
2. Create a non-root sudo user; disable root SSH login and password login (`PermitRootLogin no`, `PasswordAuthentication no`).
3. Firewall (`ufw`): allow 22/tcp (limit), 80/tcp, 443/tcp, 443/udp; deny the rest. The compose file already binds the app to loopback only (`docker-compose.yml`, `127.0.0.1:8000`).
4. `unattended-upgrades` on, `fail2ban` for SSH, timezone left to the container (`TZ=Asia/Kolkata` is set in the image and compose).
5. Install Docker Engine and the compose plugin from Docker's apt repository.

### Phase 2 — Deploy (about 1 hour)
1. Point the domain's `A` record at the VPS IP. Wait for DNS.
2. On the VPS: `git clone` the repo (use a read-only deploy key), check out a **tag** (`APP_TAG`), not a moving branch.
3. `cp .env.production.example .env.production`; set `SITE_ADDRESS`, a generated `SESSION_SECRET`, `OPENAI_API_KEY`. File mode `600`, never in git. Keep `STT_USE_HINTS=0`, `STT_TRIM_SILENCE=0` as shipped.
4. `docker compose --env-file .env.production up -d --build`. The first build downloads Chromium and takes several minutes.
5. Watch Caddy obtain the certificate; check `https://<domain>/health`.
6. `docker compose exec app python -m doctor_dictation.admin create-clinic --slug <slug> --name "<Clinic>" --first-user <user>`; note the one-time password; sign in and change it.

### Phase 3 — Smoke test on the live host (about 30 minutes)
Run on fake data. Checklist: sign in/out; dictate a short prescription (cloud STT); the review line prints the same day on screen and PDF (`Asia/Kolkata`); Save and Print give a PDF with Indian-script fonts; upload a letterhead as JPEG and as PDF (once the PDF change is merged); two clinics cannot see each other's documents; a wrong password is rejected; a 12 MB upload is refused by the proxy limit.

### Phase 4 — Backups, monitoring, updates (must finish before real data)
1. **Backup script** (new, to be written): nightly `sqlite3 .backup` of `directory.db` and each `clinics/<slug>/app.db` (safe while running), tar, encrypt (e.g. `age`), copy off-site, keep 14 daily + 8 weekly.
2. **Restore drill:** restore one backup onto a scratch folder and open it. A backup you have not restored is not a backup. Repeat monthly.
3. **Monitoring:** a free external uptime check on `/health` that alerts your phone or email; a disk-space alert at 80 percent; `docker compose logs` kept to a size cap.
4. **Updates:** tag a release, `git pull`, `docker compose up -d --build`, re-run the Phase 3 smoke test. Take a backup first (migrations only go forward, per the runbook).
5. **Secrets:** rotate the OpenAI key if it was ever pasted into a chat or ticket; set an OpenAI spend limit.

### Phase 5 — Go-live gate
All of: Phase 0 answers in writing; Phase 3 passed; Phase 4 restore drill done; first-user passwords changed; uptime alert tested by stopping the app once; rollback known (`git checkout <previous tag>`, rebuild, restore backup if a migration ran).

## Costs to expect
VPS term price (check Hostinger) + domain + OpenAI usage (Whisper per audio minute, LLM per prescription) + off-site storage (small). Set the OpenAI monthly limit before launch.

## Risks

| Risk | Mitigation |
|---|---|
| Patient data sent to a US provider | Phase 0 decision; fake data until consent text exists |
| One VPS = one failure point | Nightly off-site backup, tested restore; accept some downtime for a pilot |
| SQLite on one disk | Fine at this scale; backups are the safety net |
| Chromium memory spike | Keep `WEB_CONCURRENCY=2`; `mem_limit` in compose is documented but commented out |
| Open SSH / weak host | Keys only, ufw, fail2ban, unattended upgrades |
| Public single-mode by mistake | Image sets `MULTI_CLINIC=1`; the app refuses to start without `SESSION_SECRET` |

## Not in this plan
High availability or a second server, a managed database, a CDN, SSO, automated CI/CD, and the broader medical-compliance review (consent forms, DPA with providers); those need their own decisions.

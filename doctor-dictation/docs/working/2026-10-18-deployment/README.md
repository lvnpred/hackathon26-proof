# Pilot deployment, 2026-10-18

## Summary

The app is live for the 10-doctor pilot at `https://gsr.lightday.online` on a Hostinger KVM 2 VPS. Two clinics exist (`gsr-clinic`, `test`). Encrypted backups every 6 hours; the R2 copy is ready and becomes active once Step 9 is done. Still open before real patient data: lock SSH, confirm a restore, set an OpenAI spend limit, add an uptime alert, and decide the consent and data rules.

## What is running

| Item | Value |
|---|---|
| Host | Hostinger KVM 2: 2 vCPU, 8 GB RAM, 100 GB NVMe, Ubuntu 24.04 |
| Address | `https://gsr.lightday.online` (Cloudflare DNS, A record, "DNS only" so Caddy can get its certificate) |
| Stack | Docker compose: `app` (loopback only) and `caddy` (HTTPS, upload limits) from `docker-compose.yml` |
| Code | `main` cloned to `~/app` by `scripts/deploy/02-deploy.sh` (deploy key, read-only) |
| Server user | `deploy` (SSH key only, no password; passwordless sudo and Docker access) |
| Clinics | `gsr-clinic` (user `admin`), `test` (user `test-admin`); usernames are unique across the whole system (`doctor_dictation/accounts.py`) |
| Time zone | `TZ=Asia/Kolkata` in the image and compose |

## Decisions made

- Plan size: KVM 2. Reason: Chromium needs about 300 MiB per worker and the local speech fallback adds more; the work itself is light because speech-to-text and the LLM are cloud calls.
- OS: Ubuntu 24.04 LTS (plain OS, no control panel or Docker template).
- DNS first as "DNS only" (grey cloud); the Cloudflare proxy is optional later with SSL mode Full (strict).
- SSH hardening (`01-harden.sh --lock-ssh`) postponed by the owner; not yet applied.
- Fake data only until the consent and data rules are decided (audio and text go to OpenAI).

## Scripts (`scripts/deploy/`)

| Script | Run as | Job |
|---|---|---|
| `01-harden.sh` | root | stage 1: `deploy` user, firewall, fail2ban, automatic updates, Docker. `--lock-ssh`: turn off root and password logins |
| `02-deploy.sh <domain>` | deploy | deploy key, clone, `.env.production`, `docker compose up`, health wait |
| `03-backup.sh` | deploy | online SQLite backup of every clinic plus uploads, encrypted with `age`; server keeps 7 days (`KEEP_DAYS`), copies each archive to R2 (`RCLONE_REMOTE`, verified); `--install-cron` runs it every 6 hours (`17 */6 * * *`) |
| `restore-drill.sh` | Mac | fetch the newest R2 archive, decrypt, check every database; run monthly |

`scripts/deploy/README.md` has every step with explanations and a table of the three different keys (SSH key, backup key, deploy key).

## Problems found and fixed during rollout

| Problem | Cause | Fix |
|---|---|---|
| `ssh deploy@...` asked for a password | The test was run on the server, where the key file does not exist | Run it from the Mac |
| `--install-cron` printed nothing and left no crontab | With no crontab yet, `grep -v` exited 1 and `set -e` stopped the script silently (`03-backup.sh`) | `|| true`, plus a check that the job is in `crontab -l`; four cases tested with a stand-in `crontab` |
| A failed backup could leave a half-written file with the final name | Output written straight to the final file | Write to `.part`, rename only on success, delete on failure, log `BACKUP FAILED`, remove stale `.part` files |

## Open items

1. Run `01-harden.sh --lock-ssh` (test the `deploy` login in a second terminal first).
2. Run `restore-drill.sh` monthly; first run before real data.
3. Done when Step 9 is finished (R2 + bucket lock).
4. `.env.production` is not in the backups; keep the OpenAI key and `SESSION_SECRET` in a password manager.
5. Set an OpenAI monthly spend limit; add an uptime check on `/health`.
6. Smoke test on the `test` clinic: date format, review date, PDF, letterhead as JPEG and PDF, mic, clinic isolation.
7. Decide consent wording, retention and breach process before real patients. Also decide the backup provider: R2 is accepted for the pilot only; AWS S3 Mumbai is the fallback (pq-i owner answer Q28).
8. Done when `HC_PING_URL` is set; otherwise failures only log to `~/backup.log`.
9. Brand and trademark: `lightday.online` was chosen; no trademark search was done.
10. Archives are full copies; the server keeps 7 days; each run logs a `disk:` line in `~/backup.log`; check it monthly (size table in pq-i).

## Caveats

- The scripts were not run on a real server before the owner did; the backup and cron logic were tested locally with stand-in commands.
- The letterhead "could not read" 502 was never diagnosed; the owner's JPEG upload later worked.

## Appendix: commits

| Commit | What |
|---|---|
| 90e8b12 | Iteration 3: date localization |
| 689b6b5 | Letterhead upload accepts a PDF (page 1, pypdfium2) |
| 0fde308 | Deployment plan and setup scripts |
| 9bf466e | Backup and cron fixes, step-by-step guide |

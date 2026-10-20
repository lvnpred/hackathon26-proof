# pq-i: Off-site Backup to Cloudflare R2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every 6 hours, copy the age-encrypted backup to a Cloudflare R2 bucket, prove the copy arrived, alert on failure, and give the owner a monthly restore drill on the Mac.

**Architecture:** `scripts/deploy/03-backup.sh` keeps making the local encrypted archive exactly as today (`03-backup.sh:22-53`). After the archive is renamed, a new off-site stage uploads every local archive that R2 does not have yet (`rclone copy --ignore-existing`), then checks the newest one's size in R2. An optional healthchecks.io ping reports success or `/fail`. A new Mac-only script, `scripts/deploy/restore-drill.sh`, downloads the newest archive, decrypts it, and checks every database.

**Tech Stack:** bash, rclone (S3 backend, `provider = Cloudflare`), age, sqlite3, cron, curl, healthchecks.io (optional).

**Spec:** owner decisions given in chat on 2026-10-19 (binding, copied into Global Constraints below); `docs/superpowers/plans/2026-10-19-pq-00-index.md:23` ("Separate: off-server backup"); open items 2, 3 and 8 in `docs/working/2026-10-18-deployment/README.md:48-54`.

**Owner answers 2026-10-19:** Q27 bucket lock 30 days (verify the setting in the Cloudflare dashboard; the Cloudflare
2FA step stays). Q28 R2 is accepted for the pilot (fake data only). **Note:** revisit the provider before real patients,
together with the consent wording (deployment open item 7); AWS S3 Mumbai (`ap-south-1`) is the fallback if India
residency is needed. Q29 **changed**: local retention `KEEP_DAYS` default becomes **7** (was 14), and every run logs
disk usage (`df -h` of the backups filesystem and the archive size). Tasks 1, 3 and 5, the stand-in tests and the
owner steps are updated.

## Global Constraints

- Provider: Cloudflare R2. Bucket name: `dictdoc-backups`. Remote name in rclone: `r2`. So `RCLONE_REMOTE=r2:dictdoc-backups`.
- Schedule: every 6 hours, cron line `17 */6 * * * <script> >> $HOME/backup.log 2>&1` (00:17, 06:17, 12:17, 18:17 server time). It replaces the nightly `17 2 * * *` line (`03-backup.sh:15`).
- `--install-cron` stays idempotent and still verifies the job with `crontab -l` (`03-backup.sh:17-18`).
- Off-site retention: 90 days, by an R2 object lifecycle rule (not by the script). Bucket lock: 30 days (owner Q27).
- Provider is for the pilot (owner Q28): revisit with consent wording (deployment open item 7) before real patients; AWS S3 Mumbai is the fallback.
- Local retention: `KEEP_DAYS` default **7** (was 14, `03-backup.sh:10`; owner Q29). At 6-hourly runs that is up to 28 archives on the server.
- Disk log (owner Q29): every run that writes an archive logs `df -h` of the backups filesystem and the archive size to `~/backup.log`.
- Files are encrypted with age before upload (`03-backup.sh:48`). R2 only ever receives `*.tar.gz.age` files.
- Healthchecks.io is optional: `HC_PING_URL` unset means no ping and no error. Success pings `$HC_PING_URL`; any failure pings `$HC_PING_URL/fail`. A failed ping never changes the exit code.
- Upload failure: keep the local archive, log `OFF-SITE COPY FAILED`, exit non-zero.
- Settings for cron come from `~/.config/backup/backup.env` (mode 600). Cron passes no environment of its own.
- No network calls during implementation or tests. Tests use stand-in commands on `PATH`, like the earlier backup fixes (`docs/working/2026-10-18-deployment/README.md:42-43,59`).
- Shell scripts stay under 500 lines (project rule). Owner steps: numbered, one action per step, exact commands.

## Review Focus

1. **Cron has no `RCLONE_REMOTE`.** Today the off-site copy reads only the environment (`03-backup.sh:56`), and the cron line sets none (`03-backup.sh:15`), so the nightly job would never upload. Expected: the cron run reads `backup.env`. Pinned by Task 1 test `cron_env_reads_config`.
2. **One failed upload is never retried.** Expected: the next run uploads every local archive missing in R2. Pinned by Task 2 test `catch_up_uploads_missed_archive`.
3. **Misleading failure log.** Today a failed `rclone copy` makes the script exit non-zero, and the EXIT trap prints "BACKUP FAILED ... no file kept" (`03-backup.sh:27,57`) although the file was kept. Expected: `OFF-SITE COPY FAILED ... local copy kept at <file>`. Pinned by Task 2 test `upload_failure_keeps_local`.
4. **Disk fills up.** Full archives every 6 hours grow with the PDFs (see Size estimate). Expected: the run refuses before writing when free space is under twice the last archive, and pings `/fail`. Pinned by Task 3 test `low_disk_refuses`.
5. **Decrypted patient data left on the Mac after a drill.** Expected: the temp folder is deleted on success, on failure and on Ctrl-C. Pinned by Task 4 test `drill_cleans_temp`.

## Facts about R2 (verify the marked ones in the Cloudflare dashboard)

| Question | What R2 does | Confidence |
|---|---|---|
| Least-privilege token | R2 API tokens come as Admin Read & Write, Admin Read only, Object Read & Write, Object Read only. Object tokens can be limited to named buckets. The server gets **Object Read & Write on `dictdoc-backups` only**. The Mac gets **Object Read only on `dictdoc-backups` only**. | Sure |
| Can a write token upload but not delete? | No. Object Read & Write includes delete. There is no "write without delete" token type. | Verify in dashboard |
| rclone with an object-only token | rclone tries to create the bucket unless `no_check_bucket = true`; an object token cannot create buckets, so this option is required. | Sure |
| Deletion protection | **R2 bucket locks** (bucket Settings, "Bucket lock rules"): a rule keeps objects (by prefix) from being deleted or overwritten for a set number of days. An Object token cannot change bucket settings, so a stolen server token cannot delete locked objects. Someone logged in to the Cloudflare account can remove the rule. | Verify in dashboard |
| Lifecycle | Object lifecycle rules can delete objects N days after upload, and abort unfinished multipart uploads. | Sure |
| Location | A location hint (for example Asia-Pacific) can be chosen only at bucket creation and is best effort, not a guarantee. Jurisdictions offered: EU and FedRAMP. No India jurisdiction. | Verify in dashboard; owner decides if this matters for patient data |
| Cost | Free tier about 10 GB-month storage; then about USD 0.015 per GB-month; no egress fee. | Verify on the pricing page |

What the lock does not stop: an attacker with the server's token can still **add** objects (cost, clutter). An attacker with the owner's Cloudflare login can remove the lock. So turn on 2FA for the Cloudflare account (owner step 4).

## Size estimate

Each archive is a **full** copy of `/data` (`03-backup.sh:33-47`): `directory.db`, each `clinics/<slug>/app.db`, rendered PDFs in `clinics/<slug>/pdfs/encounter_<id>.pdf` (`doctor_dictation/db/__init__.py:48-53`, `doctor_dictation/api/persistence.py:271`), and letterhead images in `templates/` (`doctor_dictation/templates/service.py:102-106`). No audio is written to disk (no audio file write found in `doctor_dictation/`). Only `-wal`, `-shm`, `-journal` are skipped (`03-backup.sh:37`).

Local sample PDFs are 95-145 KB each (`doctor_dictation/data/pdfs/`). PDFs barely shrink under gzip. **Assumption:** 10 doctors x 20 prescriptions a day = 200 PDFs = about 25 MB of new data a day.

| Pilot age | One archive | 28 local archives (7 days) | R2 objects (90 days x 4 a day = 360) |
|---|---|---|---|
| 30 days | ~0.75 GB | ~21 GB | ~120 GB total |
| 90 days | ~2.2 GB | ~62 GB (fits the 100 GB disk, but tight) | ~400 GB, about USD 6/month |

Today, with fake data, archives are small. The free-space guard (Task 3) fails loudly before the disk fills. Measure real growth monthly with `docker compose --env-file .env.production exec app du -sh /data`. The per-run disk log line (Task 3) shows the trend in `~/backup.log` without a manual check. Lowering `KEEP_DAYS` further (for example to 3) is safe once R2 copies are verified, and is an owner decision.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `scripts/deploy/03-backup.sh` | Modify | Read `backup.env`; `KEEP_DAYS` 7; 6-hourly cron; free-space guard; disk log; off-site copy, verify, ping |
| `scripts/deploy/restore-drill.sh` | Create | Mac only: download newest, decrypt, untar to temp, check each database, clean up |
| `tests/deploy/stubs/` (`docker`, `age`, `rclone`, `curl`, `crontab`, `df`, `stat`) | Create | Stand-in commands driven by `FAKE_*` variables; no network |
| `tests/deploy/test_backup.sh` | Create | Cases for `03-backup.sh` |
| `tests/deploy/test_restore_drill.sh` | Create | Cases for `restore-drill.sh` |
| `scripts/deploy/README.md` | Modify | Step 8 wording; new Step 9 (R2) and Step 10 (drill) |
| `docs/working/2026-10-18-deployment/README.md` | Modify | Summary, scripts table, open items 2, 3, 8 |
| `docs/superpowers/plans/2026-10-19-pq-00-index.md:23` | Modify | Point "Separate" line at this plan |

---

### Task 1: Test harness, config file and 6-hourly cron

**Files:**
- Create: `tests/deploy/stubs/{docker,age,rclone,curl,crontab,df,stat}`, `tests/deploy/test_backup.sh`
- Modify: `scripts/deploy/03-backup.sh:1-20` (including `KEEP_DAYS` at `:10`)

**Interfaces:**
- Produces (stubs, used by Tasks 2-4):
  - `docker`: writes 4 KB of random bytes to stdout; `FAKE_DOCKER_FAIL=1` exits 1.
  - `age`: `cat` of stdin, or of the last argument when it is a file (covers `age -R f` and `age -d -i k file`).
  - `rclone`: a local folder `$FAKE_BUCKET` stands in for the bucket. Supports `copy SRC DST [--include P] [--ignore-existing]`, `copyto`, `lsl PATH`, `lsf PATH`. Appends each call to `$FAKE_RCLONE_LOG`. `FAKE_RCLONE_FAIL=1` exits 1 on `copy`; `FAKE_RCLONE_SHORT=1` makes `lsl` report size minus 1.
  - `curl`: appends its last argument (the URL) to `$FAKE_CURL_LOG`; `FAKE_CURL_FAIL=1` exits 22.
  - `crontab`: `-l` prints `$FAKE_CRONTAB` (exit 1 when missing); `-` writes stdin to it.
  - `df`: with `-Pk`, prints a POSIX header and one row with `$FAKE_DF_KB` (default 100000000) in the "Available" column; with `-h`, prints a header and the row `fakefs 100G 40G 60G 40% /fake` (Task 3 disk log).
  - Helper `age_file <path> <days>` in the test file: sets the file's mtime `<days>` days back with `perl -e 'utime ...'` (same on Mac and Linux).
  - `stat`: only when `uname` is Darwin, maps `-c %s F` to `/usr/bin/stat -f %z F`; else exec `/usr/bin/stat`.
- Produces (script): `BACKUP_ENV` (default `$HOME/.config/backup/backup.env`), sourced with `set -a` when it exists, **before** the defaults at `03-backup.sh:8-11`.
- Test runner: `bash tests/deploy/test_backup.sh` prints `PASS <name>` / `FAIL <name>` per case and exits non-zero on any FAIL. Each case runs in a fresh `mktemp -d` with `HOME`, `APP_DIR`, `BACKUP_DIR`, `FAKE_*` set and `PATH="tests/deploy/stubs:/usr/bin:/bin"`.

- [ ] **Step 1: Write the stubs and these failing cases in `tests/deploy/test_backup.sh`**
  - `cron_empty`: no crontab file; `--install-cron`; `$FAKE_CRONTAB` has exactly one line, matching `^17 \*/6 \* \* \* .*/03-backup.sh >> .*/backup.log 2>&1$`.
  - `cron_replaces_nightly`: crontab holds `17 2 * * * <script path> >> x 2>&1` and `0 5 * * * other-job`; after install: `other-job` line kept, no `17 2` line, one `17 */6` line.
  - `cron_twice`: install twice; still exactly one line containing the script path.
  - `cron_env_reads_config`: `backup.env` holds `RCLONE_REMOTE=fake:bucket`; run with `env -i HOME=... PATH=... BACKUP_ENV=...` (no other variables); `$FAKE_RCLONE_LOG` contains `copy`. (Fails until Task 2 adds the copy; keep it here because it pins the config read.)
  - `no_remote_local_only`: no `backup.env`; exit 0; one `data-*.tar.gz.age` in `BACKUP_DIR`; rclone log empty.
  - `keep_days_default_7` (owner Q29): no `KEEP_DAYS` set; archives aged 8 days and 6 days (`age_file`); after the run the 8-day one is gone and the 6-day one is kept.

- [ ] **Step 2: Run and confirm the cron cases fail**

Run: `bash tests/deploy/test_backup.sh`
Expected: `FAIL cron_empty`, `FAIL cron_replaces_nightly` (line still `17 2`), `PASS cron_twice`, `FAIL cron_env_reads_config`, `PASS no_remote_local_only`, `FAIL keep_days_default_7` (default still 14).

- [ ] **Step 3: Change `03-backup.sh`**
  - Header comment (`:2-6`): "every 6 hours", "keeps 7 days locally", and name `backup.env` with its two keys.
  - `:10`: `KEEP_DAYS=${KEEP_DAYS:-7}` (owner Q29; `backup.env` may still set it).
  - Before `:8`: `BACKUP_ENV=${BACKUP_ENV:-$HOME/.config/backup/backup.env}`; if it is a readable file, `set -a; . "$BACKUP_ENV"; set +a`.
  - `:15`: minute/hour fields become `17 */6 * * *`. Keep the `grep -vF "$self"` removal and the `crontab -l` check (`:17-18`) as they are; they already make the install idempotent.

- [ ] **Step 4: Run tests**

Run: `bash tests/deploy/test_backup.sh`
Expected: all PASS except `cron_env_reads_config` (Task 2). If a GNU-only flag fails on the Mac, run the same file in `docker run --rm -v "$PWD":/w -w /w ubuntu:24.04 bash tests/deploy/test_backup.sh` (sqlite3 not needed here).

- [ ] **Step 5: Commit (only if the owner asked for commits in this session)**

```bash
git add scripts/deploy/03-backup.sh tests/deploy
git commit -m "Backup: read backup.env, run every 6 hours, shell tests with stand-in commands"
```

### Task 2: Off-site copy, catch-up and size check

**Files:**
- Modify: `scripts/deploy/03-backup.sh:27` (trap) and `:55-58` (off-site stage)
- Test: `tests/deploy/test_backup.sh`

**Interfaces:**
- Consumes: stubs and `backup.env` loading from Task 1.
- Produces: variable `stage` (`local` until the `mv` at `:52`, then `offsite`); function `offsite_copy` (no arguments; uses `$OUT`, `$file`, `$RCLONE_REMOTE`); log lines `copied off-site to <remote>: <name> (<size> bytes, verified)` and `OFF-SITE COPY FAILED (<reason>); local copy kept at <file>`.

- [ ] **Step 1: Add failing cases**
  - `upload_ok`: `RCLONE_REMOTE=fake:bucket`; exit 0; `$FAKE_BUCKET/<name>` exists with the same byte size as the local file; log has `verified`.
  - `upload_failure_keeps_local`: `FAKE_RCLONE_FAIL=1`; exit non-zero; local file exists; stderr has `OFF-SITE COPY FAILED` and `local copy kept at`; stderr does **not** have `no file kept`.
  - `verify_mismatch_fails`: `FAKE_RCLONE_SHORT=1`; exit non-zero; local file exists; stderr has `size mismatch`.
  - `catch_up_uploads_missed_archive`: put `data-2026-10-18-0217.tar.gz.age` (2 KB) in `BACKUP_DIR` and not in the bucket; run; both files are in `$FAKE_BUCKET`; rclone log line for `copy` contains `--ignore-existing` and `--include data-*.tar.gz.age`.
  - `rclone_missing`: `RCLONE_REMOTE` set, stub dir without `rclone` (test builds a PATH copy minus `rclone`); exit non-zero; local file exists; stderr has `rclone not installed`.

- [ ] **Step 2: Run; expect the five new cases to FAIL** (`upload_failure_keeps_local` fails on the `no file kept` text).

- [ ] **Step 3: Implement**
  - Set `stage=local` before the trap. Trap (`:27`): keep `rm -f "$tmp"`. On non-zero exit print `BACKUP FAILED (exit $rc); no file kept` only when `stage=local`; when `stage=offsite`, the off-site function has already printed its own line.
  - Set `stage=offsite` right after `mv` (`:52`). Keep the local prune at `:55` before the copy (it only removes archives older than `KEEP_DAYS`, default 7).
  - `offsite_copy`, called only when `RCLONE_REMOTE` is non-empty:
    1. `command -v rclone` or fail with reason `rclone not installed`.
    2. `rclone copy "$OUT" "$RCLONE_REMOTE" --include 'data-*.tar.gz.age' --ignore-existing` or fail with reason `rclone copy exit <n>`. `--ignore-existing` never overwrites a remote object, so a bucket lock never blocks it, and every earlier missed archive goes up now.
    3. `remote=$(rclone lsl "$RCLONE_REMOTE/$(basename "$file")" | awk 'NR==1{print $1}')`; compare with `$size` (`:50`); unequal or empty fails with reason `size mismatch local=<a> remote=<b>`.
    4. Each failure prints the `OFF-SITE COPY FAILED` line to stderr and `exit 1`. The local file is never touched.

- [ ] **Step 4: Run tests; expect all PASS, including `cron_env_reads_config` from Task 1.**

- [ ] **Step 5: Commit (only if asked)** — message: `Backup: verified R2 copy with catch-up; upload failure keeps the local file`.

### Task 3: Healthchecks ping, free-space guard and disk log

**Files:**
- Modify: `scripts/deploy/03-backup.sh` (trap at `:27`, new guard before `:31`, end of script)
- Test: `tests/deploy/test_backup.sh`

**Interfaces:**
- Consumes: `stage`, trap from Task 2.
- Produces: function `hc_ping <suffix>` (`""` or `/fail`); does nothing when `HC_PING_URL` is empty; runs `curl -fsS -m 10 --retry 3 -o /dev/null "$HC_PING_URL$1"`; on curl failure prints `warning: healthchecks ping failed` and returns 0.
- Produces (owner Q29): function `log_disk` (no arguments; uses `$OUT`, `$size`); prints `<date -Is> disk: <df -h "$OUT" data row>; archive <size> bytes` to stdout (so to `~/backup.log` under cron). A `df` failure prints `disk: unknown` and never fails the run.

- [ ] **Step 1: Add failing cases**
  - `hc_success`: `HC_PING_URL=https://hc.example/abc`; exit 0; `$FAKE_CURL_LOG` is exactly `https://hc.example/abc`.
  - `hc_fail_on_local_error`: plus `FAKE_DOCKER_FAIL=1`; exit non-zero; curl log is exactly `https://hc.example/abc/fail`.
  - `hc_fail_on_upload_error`: plus `RCLONE_REMOTE`, `FAKE_RCLONE_FAIL=1`; curl log ends with `/fail`.
  - `hc_unset_no_curl`: no `HC_PING_URL`; curl log absent.
  - `hc_curl_down_still_ok`: `FAKE_CURL_FAIL=1`; exit 0; stderr has `healthchecks ping failed`.
  - `low_disk_refuses`: a previous 2 KB archive exists; `FAKE_DF_KB=3`; exit non-zero; no new archive; stderr has `low disk`; curl log ends with `/fail`.
  - `logs_disk_usage` (owner Q29): plain run; exit 0; stdout has one line matching `disk: fakefs 100G 40G 60G 40% /fake; archive [0-9]+ bytes`, and the number equals the new archive's byte size.
  - `logs_disk_usage_with_upload`: plus `RCLONE_REMOTE=fake:bucket`; the disk line is still printed (before the off-site copy).

- [ ] **Step 2: Run; expect the eight new cases to FAIL.**

- [ ] **Step 3: Implement**
  - Define `hc_ping` before the trap. In the trap, on non-zero `rc` call `hc_ping /fail`. At the end of a successful run call `hc_ping ""`.
  - Guard before `:31`: `last` = size in bytes of the newest `data-*.tar.gz.age` in `$OUT` (0 if none); `free` = `df -Pk "$OUT" | awk 'NR==2{print $4*1024}'`; when `free < 2 * last` or `free < 1073741824` (1 GiB), fail with `low disk: <free> bytes free, last backup <last> bytes`. The test sets `FAKE_DF_KB=3`, which is below both.
  - Call `log_disk` right after the local prune (`:55`) and before `offsite_copy`, so every run that kept an archive logs the disk, even when the upload then fails.

- [ ] **Step 4: Run tests; expect all PASS.**

- [ ] **Step 5: Commit (only if asked)** — message: `Backup: optional healthchecks.io ping, refuse when the disk is nearly full, log disk usage each run`.

### Task 4: Restore drill script (Mac, monthly, manual)

**Files:**
- Create: `scripts/deploy/restore-drill.sh`, `tests/deploy/test_restore_drill.sh`

**Interfaces:**
- Consumes: `rclone`, `age` stubs from Task 1 (the age stub is `cat`, so fixtures are plain `.tar.gz` named `.age`).
- Produces: `bash scripts/deploy/restore-drill.sh [--file <archive.age>]`. Variables: `RESTORE_REMOTE` (default `r2-read:dictdoc-backups`), `AGE_KEY` (default `$HOME/dictdoc-backup.key`), `MAX_AGE_HOURS` (default 12). Exit 0 only when every database says `ok`.

- [ ] **Step 1: Write failing cases.** A helper builds a fixture: `directory.db`; `clinics/a/app.db` with tables `documents` (2 rows) and `clinic_formulary` (1 row); `clinics/a/pdfs/encounter_1.pdf`; tar-gz into `$FAKE_BUCKET/data-2026-10-19-0617.tar.gz.age`, plus an older `data-2026-10-18-0017.tar.gz.age` holding a different clinic `b`.
  - `drill_picks_newest`: output names `data-2026-10-19-0617.tar.gz.age` and clinic `a`, not `b`.
  - `drill_ok`: exit 0; output has `directory.db: ok` and `clinics/a/app.db: ok documents=2 clinic_formulary=1 pdfs=1`.
  - `drill_corrupt_db_fails`: fixture where `clinics/a/app.db` is 4 KB of random bytes; exit non-zero; output has `clinics/a/app.db: FAILED`.
  - `drill_cleans_temp`: `TMPDIR` set to an empty test folder; after both an ok and a failing run, that folder is empty.
  - `drill_local_file`: `--file <path>` with no bucket; exit 0; rclone log empty.
  - `drill_stale_warns`: newest name older than `MAX_AGE_HOURS`; output has `WARNING: newest backup is` (exit stays 0; staleness is the healthchecks job).

- [ ] **Step 2: Run `bash tests/deploy/test_restore_drill.sh`; expect FAIL (script missing).**

- [ ] **Step 3: Implement `restore-drill.sh`**
  - `set -euo pipefail`; `umask 077`; `work=$(mktemp -d)`; `trap 'rm -rf "$work"' EXIT INT TERM`. The folder holds decrypted patient data; nothing is copied elsewhere.
  - Check `age`, `sqlite3`, `tar` (and `rclone` unless `--file`) are installed; check `$AGE_KEY` exists.
  - Newest: `rclone lsf "$RESTORE_REMOTE" --include 'data-*.tar.gz.age' | sort | tail -n1` (names sort by time: `data-%F-%H%M`, `03-backup.sh:25`). Download with `rclone copyto`.
  - Staleness: parse the timestamp from the name; warn when older than `MAX_AGE_HOURS`.
  - `age -d -i "$AGE_KEY" "$archive" | tar xz -C "$work/data"`.
  - For `directory.db` and each `clinics/*/app.db`: `sqlite3 -readonly "$db" 'PRAGMA integrity_check;'` must print exactly `ok`. For app.db also `SELECT COUNT(*) FROM documents;`, `SELECT COUNT(*) FROM clinic_formulary;` (tables from `doctor_dictation/db/migrations/001_init.sql:39`, `009_clinic_formulary.sql:4`) and count `pdfs/*.pdf`. One line per database, then `Drill passed` or `Drill FAILED`.

- [ ] **Step 4: Run both test files; expect all PASS.**

- [ ] **Step 5: Commit (only if asked)** — message: `Restore drill script for the Mac`.

### Task 5: Owner guide and deployment record

**Files:**
- Modify: `scripts/deploy/README.md:119-138`, `docs/working/2026-10-18-deployment/README.md:5,33,48-54`, `docs/superpowers/plans/2026-10-19-pq-00-index.md:23`

- [ ] **Step 1: `scripts/deploy/README.md` Step 8 (`:119-138`).** Change "nightly at 02:17" to "every 6 hours (00:17, 06:17, 12:17, 18:17)"; state "the server keeps 7 days of archives (`KEEP_DAYS`, default 7)" and "each run writes a `disk:` line to `~/backup.log`". Keep the `age-recipient.txt` commands. Replace the **Gap** paragraph (`:138`) with "Next: Step 9 copies backups off the server."
- [ ] **Step 2: Add "Step 9. Off-site copy to Cloudflare R2"** with a "What and why" line (the server copy dies with the server; R2 only ever sees encrypted files) and the owner steps below, verbatim.
- [ ] **Step 3: Add "Step 10. Monthly restore drill (Mac)"** with the drill steps below.
- [ ] **Step 4: Deployment record.** Line 5: "Encrypted backups every 6 hours, copied to Cloudflare R2". Line 33: the new schedule and R2 copy; add a row for `restore-drill.sh` (Mac). Open items: 2 becomes "Run `restore-drill.sh` monthly; first run before real data"; 3 becomes "Done when Step 9 is finished (R2 + bucket lock)"; 8 becomes "Done when `HC_PING_URL` is set; otherwise failures only log to `~/backup.log`". Add item: "Archives are full copies; the server keeps 7 days; each run logs a `disk:` line in `~/backup.log`; check it monthly (size table in pq-i)". Item 7 gains: "Also decide the backup provider: R2 is accepted for the pilot only; AWS S3 Mumbai is the fallback (pq-i owner answer Q28)".
- [ ] **Step 5: Index.** `pq-00-index.md:23`: "Separate: off-server backup, `2026-10-19-pq-i-offsite-backup.md`".
- [ ] **Step 6: Check.** Run `bash tests/deploy/test_backup.sh && bash tests/deploy/test_restore_drill.sh`; read Step 9 top to bottom against the script's variable names (`RCLONE_REMOTE`, `HC_PING_URL`, `backup.env`).
- [ ] **Step 7: Commit (only if asked)** — message: `Docs: R2 off-site backup and restore drill steps`.

#### Owner steps for Step 9 (Cloudflare dashboard, then server)

Cloudflare dashboard:
1. Open R2 > Create bucket. Name it `dictdoc-backups`. Choose the location hint (Asia-Pacific is nearest to India; see Facts table). Create it.
2. Open the bucket > Settings > Object lifecycle rules. Add a rule for the whole bucket: delete objects 90 days after upload.
3. In the same Settings page, find "Bucket lock rules". Add a rule for the whole bucket: retain 30 days (owner Q27). Check that the saved rule shows 30 days. If the page has no such section, stop and tell the developer.
4. Turn on two-factor login for the Cloudflare account (My Profile > Authentication). The lock only protects against a stolen server, not a stolen Cloudflare login.
5. Open R2 > Manage API tokens > Create API token. Permission: Object Read & Write. Apply to: `dictdoc-backups` only. Name: `dictdoc-vps-backup`. Create.
6. Copy the Access Key ID, the Secret Access Key and the S3 endpoint (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`) into your password manager. The secret is shown once.
7. Create a second token: Object Read only, `dictdoc-backups` only, name `dictdoc-mac-restore`. Save its keys too.

Healthchecks.io (optional):
8. At healthchecks.io create a check. Schedule: period 6 hours, grace 1 hour. Copy its ping URL.

Server (`ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10`):
9. Copy the new script from the Mac first: `scp -i ~/.ssh/id_ed25519_dictdoc_vps scripts/deploy/03-backup.sh deploy@200.234.34.10:~/` (run on the Mac, in the repo folder).
10. Install rclone: `sudo apt-get update && sudo apt-get install -y rclone`
11. Check it knows R2: `rclone version` (any 1.59 or newer) and `rclone help backend s3 | grep -i cloudflare` (prints a line).
12. Make the config file, private from the start: `mkdir -p ~/.config/rclone && install -m 600 /dev/null ~/.config/rclone/rclone.conf`
13. Open it: `nano ~/.config/rclone/rclone.conf`. Paste the block below with your three values. Save with Ctrl-O, Enter, Ctrl-X. (Typing keys in an editor keeps them out of shell history.)

```ini
[r2]
type = s3
provider = Cloudflare
access_key_id = <ACCESS_KEY_ID>
secret_access_key = <SECRET_ACCESS_KEY>
region = auto
endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
acl = private
no_check_bucket = true
```

14. Test the login: `rclone lsf r2:dictdoc-backups` — prints nothing and no error.
15. Make the backup settings file: `install -m 600 /dev/null ~/.config/backup/backup.env && nano ~/.config/backup/backup.env`
16. Put these lines in it (leave out `HC_PING_URL` if you skipped step 8): `RCLONE_REMOTE=r2:dictdoc-backups` and `HC_PING_URL=https://hc-ping.com/<your-uuid>`
17. Run one backup now: `bash ~/03-backup.sh` — the output has a `disk:` line (size, used, free of the backups disk, and the archive size), and the last line reads `copied off-site to r2:dictdoc-backups: data-... (... bytes, verified)`.
18. Replace the nightly job: `bash ~/03-backup.sh --install-cron`
19. Confirm: `crontab -l` shows one line starting `17 */6 * * *` and no `17 2` line.
20. Test the lock: `rclone deletefile r2:dictdoc-backups/<the file from step 17>` — it must fail with an access or lock error. If it succeeds, the lock is not on; repeat step 3.
21. Check the alert (if step 8 done): healthchecks.io shows the check green within a minute.
22. Next day, check the disk log: `grep 'disk:' ~/backup.log | tail -n 4` — four lines, one per run; the `Use%` column stays well under 80%.

#### Owner steps for Step 10 (Mac, first of each month)

1. Install tools once: `brew install rclone age`
2. Configure the read-only remote once: `mkdir -p ~/.config/rclone && install -m 600 /dev/null ~/.config/rclone/rclone.conf`, then add a `[r2-read]` block like step 13 with the `dictdoc-mac-restore` keys.
3. Run the drill: `bash scripts/deploy/restore-drill.sh`
4. Read the result: every line ends `ok`, counts look right, last line `Drill passed`.
5. Write the date and result in `docs/working/2026-10-18-deployment/README.md` under open item 2.
6. On the server, check the disk trend: `grep 'disk:' ~/backup.log | tail -n 30`. If `Use%` passes 70%, tell the developer.

---

## Out of scope (deliberately)

- Incremental or deduplicated backups (restic/borg); every archive stays a full copy as today.
- `.env.production` stays out of backups (`docs/working/2026-10-18-deployment/README.md:50`).
- Rotating `~/backup.log` (about 4 lines a run; small).
- Changing the 14-daily + 8-weekly idea in `2026-10-18-hostinger-vps-deployment.md:50`; the owner's 90-day rule replaces it.
- Running anything on the server; the owner runs the steps above.

## Open questions for the owner (answered 2026-10-19)

1. Bucket lock length: **30 days** (Q27). It stays shorter than the 90-day lifecycle so old copies can still be deleted.
2. Location and data residency: **R2 accepted for the pilot** (fake data) (Q28). Revisit before real patients with the consent wording (deployment open item 7); fallback AWS S3 Mumbai.
3. Local retention: **`KEEP_DAYS` default 7**, plus a disk log line every run (Q29).

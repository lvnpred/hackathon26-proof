# Running the live server (gsr.lightday.online)

## Summary

This guide is for running the live pilot once it is set up. First-time setup (hardening, first deploy, first clinic) is in
`scripts/deploy/README.md`.

| Job | How often | Where |
|---|---|---|
| Update the app to the latest `main` | When a new version is pushed | [Section 2](#2-update-the-app) |
| Glance at the backup log | Weekly | [Section 5](#5-check-the-backups) |
| Restore drill on the Mac | 1st of each month | [Section 6](#6-monthly-restore-drill-mac) |
| Restore real data | Only after data loss | [Section 7](#7-restore-for-real) |
| Fix something | When it breaks | [Section 8](#8-troubleshooting) |

Backups run by themselves every 6 hours. Each one is encrypted on the server, kept there 7 days and copied to Cloudflare
R2, which keeps it 90 days and refuses to delete it for the first 30. Only your Mac holds the key that opens them.

**Never paste** the OpenAI key, the R2 secret keys, `~/dictdoc-backup.key` or `.env.production` into chat, email or tickets.

---

## 1. The system at a glance

```
Doctors ──https──> Caddy (HTTPS) ──> App (container, 2 workers) ──> /data volume (SQLite databases, uploads)
                                                                         │
                           every 6 h: 03-backup.sh ── encrypt (age) ──> ~/backups (7 days)
                                                                         │ rclone
                                                                         ▼
                                                     Cloudflare R2: dictdoc-backups (90 days; locked 30)
                                                                         │ read-only key
Your Mac: restore-drill.sh ── decrypt with ~/dictdoc-backup.key ◄────────┘
```

| Thing | Value |
|---|---|
| Site | https://gsr.lightday.online |
| Server | `deploy@200.234.34.10` (Hostinger KVM 2, Ubuntu 24.04) |
| SSH from the Mac | `ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10` |
| App folder | `~/app` (a git checkout of `main`) |
| App settings | `~/app/.env.production` (mode 600; updates never change it) |
| Data | Docker volume `doctor-dictation_data`, mounted at `/data` in the app (`directory.db`, `clinics/<slug>/app.db`, uploads) |
| Certificates | Docker volume `caddy_data` (not backed up; Caddy re-issues them if lost) |
| Backups on the server | `~/backups/data-YYYY-MM-DD-HHMM.tar.gz.age`, log in `~/backup.log` |
| Backup settings | `~/.config/backup/age-recipient.txt` (public key), `~/.config/backup/backup.env` |
| R2 login (server) | `~/.config/rclone/rclone.conf`, section `[r2]`, read and write |
| R2 login (Mac) | `~/.config/rclone/rclone.conf`, section `[r2-read]`, read only |

### Keys and secrets

| Secret | Lives | Used for | If lost |
|---|---|---|---|
| SSH key `~/.ssh/id_ed25519_dictdoc_vps` | Mac | Logging in to the server | Add a new key in the Hostinger panel |
| Backup private key `~/dictdoc-backup.key` | Mac and password manager, **never the server** | Opening backups | Every backup becomes unreadable. Keep two copies. |
| Backup public key (`age1...`) | Server, `age-recipient.txt` | Encrypting backups | Copy it again from the private key's file |
| Deploy key `~/.ssh/deploy_key` | Server | Downloading code from GitHub (read only) | Delete it, rerun `02-deploy.sh`, add the new key in GitHub |
| R2 token `dictdoc-vps-backup` | Server `rclone.conf`, password manager | Uploading backups | Make a new token in Cloudflare, edit `rclone.conf` |
| R2 token `dictdoc-mac-restore` | Mac `rclone.conf`, password manager | Reading backups | Make a new read-only token |
| `OPENAI_API_KEY`, `SESSION_SECRET` | Server `.env.production` | AI and login cookies | New OpenAI key; a new session secret signs everyone out |

---

## 2. Update the app

About 10 minutes. The site is down for a few seconds while the container swaps, so update outside clinic hours.

**Mac:** log in.
```
ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10
```

**Server:**
1. Back up now:
   ```
   bash ~/03-backup.sh
   ```
   The last line should say `copied off-site ... verified`.
2. Write down the current version, for a rollback:
   ```
   git -C ~/app log -1 --oneline
   ```
3. Update:
   ```
   bash ~/02-deploy.sh gsr.lightday.online
   ```
   It pulls `main` (fast-forward only), keeps `.env.production`, rebuilds and waits for the health check. It ends with
   `Healthy.` and a table with `app` and `caddy` running.
4. Check the new version:
   ```
   git -C ~/app log -1 --oneline
   ```
   It must match the newest commit on GitHub.
5. If this update changed `scripts/deploy/03-backup.sh`, refresh the copy that cron runs:
   ```
   cp ~/app/scripts/deploy/03-backup.sh ~/03-backup.sh
   ```
6. Once, on the first update that brings spoken hints (plan SH-H1), count the saved prescriptions into each
   doctor's spoken terms:
   ```
   cd ~/app && docker compose --env-file .env.production exec app python -m doctor_dictation.admin backfill-spoken-terms
   ```
   Until it runs, each doctor's own hints are empty and only new saves fill them. It prints one line per clinic:
   `<clinic>: N documents read, M new term uses`. It is safe to run twice: the second run counts nothing. It exits 1
   and prints `<clinic>: FAILED ...` if a clinic database failed; the other clinics are still counted. Fix the cause
   and run it again.
   Run it once more on the first update that brings diagnosis links (plan SH-H3): it then also teaches each
   doctor's links between diagnoses and terms from the saved prescriptions. Until it runs, only new saves teach links.

**Browser** (https://gsr.lightday.online):
1. Log in and dictate one short prescription.
2. Confirm any flagged rows, then Save.
3. Print it and check the layout.
4. Reopen it from Today. Confirmed rows should not ask again.

### Roll back
Use the version you wrote down in step 2:
```
cd ~/app && git checkout <old-commit> && docker compose --env-file .env.production up -d --build
```
A newer version can add database tables. The older code has not been tested against them. If the older version
misbehaves, restore the backup from step 1 ([Section 7](#7-restore-for-real)). The next `02-deploy.sh` run returns to `main`.

### Optional settings
Add a line to `~/app/.env.production`, then apply it without a rebuild:
```
cd ~/app && docker compose --env-file .env.production up -d
```

| Setting | Why |
|---|---|
| `OWNER_USERNAMES=<your username>` | Opens the owner screen for clinic list changes. Without it the screen answers 404. |

---

## 3. How backups work

1. Every 6 hours (00:17, 06:17, 12:17, 18:17 server time), cron runs `~/03-backup.sh`.
2. The script copies every SQLite database while the app keeps running (SQLite's online backup), adds the uploaded files,
   compresses them and encrypts the result with the public key. It refuses to write an unencrypted file.
3. It saves the archive in `~/backups` and deletes local archives older than 7 days.
4. It copies every archive R2 does not have yet (`rclone copy --ignore-existing`), then checks that the new archive's size
   in R2 equals the local size. Only then does it print `copied off-site ... verified`.
5. If healthchecks.io is set up, it pings the check: success, or `/fail` on any error.

| Copy | Kept | Can be deleted early? |
|---|---|---|
| Server, `~/backups` | 7 days (`KEEP_DAYS`) | Yes, by anyone on the server |
| Cloudflare R2 | 90 days (lifecycle rule) | No, not in the first 30 days (bucket lock) |

**What the lock protects against:** someone who breaks into the server has the R2 upload key. The lock stops them from
deleting or overwriting the last 30 days of backups. It does not protect against a stolen Cloudflare login, so keep
two-factor login on.

**One limit:** if uploads fail for more than 7 days, archives that never reached R2 are deleted from the server. Act on a
`/fail` alert or an `OFF-SITE COPY FAILED` line within a week.

---

## 4. Off-site backup setup (Cloudflare R2)

Done on 2026-10-20. Repeat only on a new server or a new Cloudflare account.

### 4.1 Cloudflare dashboard
1. Go to R2 › Create bucket. Name it `dictdoc-backups`, set the location hint to Asia-Pacific and create it.
2. Go to Bucket › Settings › Object lifecycle rules. Add a rule for the whole bucket: delete objects 90 days after upload.
3. On the same page, go to Bucket lock rules. Add a rule for the whole bucket: retain 30 days. Check that the saved rule
   shows 30 days.
4. Turn on two-factor login (My Profile › Authentication).
5. Go to R2 › Manage API tokens › Create API token. Choose Object Read & Write, bucket `dictdoc-backups` only, and name it
   `dictdoc-vps-backup`.
6. Save the Access Key ID, the Secret Access Key and the endpoint (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`) in
   the password manager. The secret is shown once.
7. Make a second token for the Mac: Object Read only, `dictdoc-backups` only, named `dictdoc-mac-restore`. Save its keys
   too.
8. Optional: at healthchecks.io, create a check with period 6 hours and grace 1 hour. Copy its ping URL.

### 4.2 Server
1. Copy the newest backup script:
   ```
   cp ~/app/scripts/deploy/03-backup.sh ~/03-backup.sh
   ```
2. Install rclone:
   ```
   sudo apt-get update && sudo apt-get install -y rclone
   ```
3. Check that rclone knows R2. The version must be 1.59 or newer, and the second command must print a line.
   ```
   rclone version
   rclone help backend s3 | grep -i cloudflare
   ```
4. Make the config file, private from the start:
   ```
   mkdir -p ~/.config/rclone && [ -f ~/.config/rclone/rclone.conf ] || install -m 600 /dev/null ~/.config/rclone/rclone.conf
   ```
5. Open it with `nano ~/.config/rclone/rclone.conf` and type the block below. **The first line must be `[r2]`, and no
   line may start with spaces.** Save with Ctrl-O, Enter, Ctrl-X.
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
   no_head = true
   ```
   `no_head = true` stops rclone reading each upload back with `?versionId=`, which R2 answers with a 501 (see
   Troubleshooting). The backup script checks the uploaded size itself.
6. Check the remote. `rclone listremotes` must print `r2:`. `rclone lsf r2:dictdoc-backups` prints the file list (empty
   at first) and no error.
   ```
   rclone listremotes
   rclone lsf r2:dictdoc-backups
   ```
7. Make the backup settings file:
   ```
   install -m 600 /dev/null ~/.config/backup/backup.env && nano ~/.config/backup/backup.env
   ```
   Put in these lines, with no leading spaces. Leave out `HC_PING_URL` if you skipped healthchecks.io.
   ```
   RCLONE_REMOTE=r2:dictdoc-backups
   HC_PING_URL=https://hc-ping.com/<your-uuid>
   ```
8. Run one backup. The last line must read `copied off-site to r2:dictdoc-backups: data-... (... bytes, verified)`.
   ```
   bash ~/03-backup.sh
   ```
9. Install the 6-hour schedule:
   ```
   bash ~/03-backup.sh --install-cron
   crontab -l
   ```
   `crontab -l` must show exactly one backup line, `17 */6 * * * /home/deploy/03-backup.sh >> /home/deploy/backup.log 2>&1`.
10. Compare the two lists. Every server archive must be in R2 with the same size.
    ```
    rclone lsl r2:dictdoc-backups
    ls -l ~/backups
    ```
11. Test the lock with the archive from step 8. **The delete must fail** with an access or lock error. If it succeeds,
    the lock is off: redo 4.1 step 3.
    ```
    rclone deletefile r2:dictdoc-backups/<archive from step 8>
    ```
12. If healthchecks.io is set up, the check turns green within a minute.

### 4.3 Mac (once, for restores)
1. Install the tools:
   ```
   brew install rclone age
   ```
2. Make the config file:
   ```
   mkdir -p ~/.config/rclone && [ -f ~/.config/rclone/rclone.conf ] || install -m 600 /dev/null ~/.config/rclone/rclone.conf
   ```
3. Open it with `nano ~/.config/rclone/rclone.conf` and add this block with the read-only keys. The first line must be
   `[r2-read]`.
   ```ini
   [r2-read]
   type = s3
   provider = Cloudflare
   access_key_id = <MAC_RESTORE_ACCESS_KEY_ID>
   secret_access_key = <MAC_RESTORE_SECRET_ACCESS_KEY>
   region = auto
   endpoint = https://<ACCOUNT_ID>.r2.cloudflarestorage.com
   acl = private
   no_check_bucket = true
   ```
4. Run the drill once ([Section 6](#6-monthly-restore-drill-mac)).

---

## 5. Check the backups

**Weekly, on the server:**
```
tail -n 20 ~/backup.log
grep -E "FAILED|Attempt 3/3" ~/backup.log | tail
grep 'disk:' ~/backup.log | tail -n 4
```
- The first command should show recent `wrote ...` and `copied off-site ... verified` lines, four runs a day.
- The second command should print nothing.
- In the third, the `Use%` column should stay well under 70%.

**Healthchecks.io**, if set up, emails you when a run fails or does not happen within 7 hours. Green means fine.

---

## 6. Monthly restore drill (Mac)

A backup you have never opened is a hope, not a backup. On the 1st of each month:
1. From the repo folder on the Mac, run the drill:
   ```
   bash scripts/deploy/restore-drill.sh
   ```
2. Read the result:
   - Every database line ends `: ok`.
   - The clinic lines show counts, and the counts look right.
   - The last line is `Drill passed`.
3. If you see `WARNING: newest backup is ...h old`, the off-site copy is stale. Check [Section 5](#5-check-the-backups).
   The warning can be off by the time-zone difference between the Mac and the server.
4. Write the date and the result in `docs/working/2026-10-18-deployment/README.md`.

The drill downloads the newest archive, decrypts it into a private temporary folder, checks every database and deletes
the folder. To use other values, set them before the command:
- `RESTORE_REMOTE` (default `r2-read:dictdoc-backups`);
- `AGE_KEY` (default `~/dictdoc-backup.key`);
- `MAX_AGE_HOURS` (default 12).

To check a file you already downloaded, use `--file <archive.age>`.

---

## 7. Restore for real

**The decrypted archive is patient data.** Keep it in a private folder, and delete it on the Mac and the server when you
finish. This procedure has not been rehearsed on the live server yet. Rehearse it once on a test server before you need it.

### 7.1 The server works, but the data is wrong or lost

**Mac:** fetch and decrypt the archive you want. Usually that is the newest one from before the problem.
```
mkdir -m 700 ~/dictdoc-restore && cd ~/dictdoc-restore
rclone lsf r2-read:dictdoc-backups | sort | tail -n 8
rclone copy r2-read:dictdoc-backups/<archive>.tar.gz.age .
age -d -i ~/dictdoc-backup.key <archive>.tar.gz.age > data.tar.gz
tar tzf data.tar.gz | head
scp -i ~/.ssh/id_ed25519_dictdoc_vps data.tar.gz deploy@200.234.34.10:~/
```
`tar tzf` must list `directory.db` and `clinics/gsr/app.db`.

**Server:**
1. Keep a copy of the current state, even a bad one:
   ```
   bash ~/03-backup.sh
   ```
2. Stop the app (Caddy keeps running):
   ```
   cd ~/app && docker compose --env-file .env.production stop app
   ```
3. Replace the data. The app runs as user id 10001, so the files must belong to it.
   ```
   mkdir -m 700 -p ~/restore && mv ~/data.tar.gz ~/restore/
   docker run --rm -v doctor-dictation_data:/data -v "$HOME/restore":/restore docker.io/library/alpine \
     sh -c 'rm -rf /data/* /data/.[!.]* ; tar xzf /restore/data.tar.gz -C /data && chown -R 10001:10001 /data'
   ```
4. Start the app and check its health:
   ```
   docker compose --env-file .env.production start app
   curl -fsS https://gsr.lightday.online/health && echo OK
   ```
5. Log in and open a few recent prescriptions.
6. Delete the decrypted copy:
   ```
   rm -rf ~/restore
   ```

**Mac:** delete the decrypted copy.
```
rm -rf ~/dictdoc-restore
```

### 7.2 The server is gone
1. Rent a new server, then follow `scripts/deploy/README.md` steps 2 to 5 (harden, log in, copy the scripts, deploy).
   Skip step 6: the clinic comes back with the data.
2. Put the same public key in `~/.config/backup/age-recipient.txt`.
3. Restore the data as in 7.1. Skip the server's step 1, because there is nothing to keep yet.
4. Point the DNS record for `gsr.lightday.online` at the new server's address. The Cloudflare record must stay grey
   ("DNS only").
5. Set up the off-site copy again: section 4.2, steps 2 to 12.

---

## 8. Troubleshooting

### Logging in and updating

| Symptom | Cause | Fix |
|---|---|---|
| `Permission denied (publickey)` | Wrong key file, or the key is not on the server | Use `-i ~/.ssh/id_ed25519_dictdoc_vps`; check the key in the Hostinger panel |
| `Docker is not usable by this user` | The `deploy` user's group change has not taken effect yet | Log out and in again |
| `WARNING: gsr.lightday.online resolves to ...` | DNS points elsewhere | `dig +short gsr.lightday.online @1.1.1.1` must print the server IP; the Cloudflare record must be grey |
| No `Healthy.` after 5 minutes | App or Caddy failed to start | `cd ~/app && docker compose --env-file .env.production logs --tail 100 app` (or `caddy`) |
| `git pull` / `checkout` refuses: local changes | Files in `~/app` were edited by hand | `git -C ~/app status`; keep anything you need, then `git -C ~/app checkout -- .` |
| `Not possible to fast-forward` | `~/app` has commits that are not on GitHub | `git -C ~/app log origin/main..HEAD`; never edit code on the server |
| Site works but shows old screens | The browser cached the old page | Hard refresh (Cmd-Shift-R) |

### rclone and R2

| Symptom | Cause | Fix |
|---|---|---|
| `didn't find section in config file`; `rclone listremotes` prints `DEFAULT:` | The `[r2]` header line is missing, and that was the cause on 2026-10-20 | `sed -i '1i [r2]' ~/.config/rclone/rclone.conf` |
| Same error, header present | Leading spaces or Windows line endings | `sed -E 's/=.*/= …/' ~/.config/rclone/rclone.conf \| cat -A` shows the structure with values masked; remove leading spaces; `sed -i 's/\r$//' ~/.config/rclone/rclone.conf` |
| `rclone config file` names another path | Run with `sudo` or as another user | Run as `deploy`, without sudo |
| `SignatureDoesNotMatch` or `AccessDenied` on `lsf` | Wrong key ID, secret or endpoint, or a token for another bucket | Recheck them in `nano`; the token must cover `dictdoc-backups` |
| `NotImplemented: Not Implemented, status code: 501` errors, then `Attempt 2/3 succeeded` | After the upload (which works), rclone 1.60 reads the object back as `HEAD …?versionId=…`; R2 does not support `versionId` and answers 501. Found on 2026-10-22: every run hit it; every archive still arrived complete. | Add `no_head = true` to the `[r2]` section (4.2 step 5). The script's own size check still verifies each copy. |
| `rclone deletefile` on a new archive succeeds | The bucket lock is off | Redo 4.1 step 3 at once |

### Backup script messages

| Message | Cause | Fix |
|---|---|---|
| `OFF-SITE COPY FAILED (size mismatch local=... remote=...)` right after a manual run | Two runs in the same minute give the same name. R2 keeps the first and never overwrites it, so the sizes differ. | Nothing is lost: both are valid backups. Wait a minute between manual runs. |
| `OFF-SITE COPY FAILED (rclone copy exit N)` | Network, R2 or login problem | Run `rclone lsf r2:dictdoc-backups` to see the error. The next run uploads every missed archive. Fix within 7 days. |
| `OFF-SITE COPY FAILED (rclone not installed)` | rclone missing | `sudo apt-get install -y rclone` |
| `off-site copy: skipped (RCLONE_REMOTE not set)` | `backup.env` missing, unreadable or misspelled | Check `~/.config/backup/backup.env`; the line must be `RCLONE_REMOTE=r2:dictdoc-backups` |
| `No age public key at ...; refusing to write an unencrypted backup` | `age-recipient.txt` missing or empty | Put the `age1...` public key back (`scripts/deploy/README.md` step 8) |
| `low disk: ... bytes free` | Less than 1 GiB, or less than twice the last archive | `df -h`; remove old Docker images with `docker image prune` |
| `another backup is running; skipped` | The previous run is still going | Nothing to do; if it repeats, look for a stuck process with `ps aux \| grep 03-backup` |
| `Backup looks empty (... bytes)` | The copy inside the app container failed, usually because the app is not running | `docker compose --env-file .env.production ps`; start it, then run again |
| `warning: healthchecks ping failed` | The server could not reach healthchecks.io | Only the alert is affected, not the backup |

### Restore drill (Mac)

| Message | Cause | Fix |
|---|---|---|
| `ERROR: AGE_KEY file not found` | The private key is not at `~/dictdoc-backup.key` | Restore it from the password manager, or set `AGE_KEY=...` |
| `no identity matched any of the recipients` | The archive was encrypted for another public key | Use the matching private key; check `age-recipient.txt` on the server |
| `WARNING: newest backup is ...h old` | The off-site copy is stale | See [Section 5](#5-check-the-backups) |
| `Drill FAILED`, or a database line is not `: ok` | A damaged archive or database | Try the previous archive; report it |

---

## 9. Checklist

| When | Do |
|---|---|
| After every update | `Healthy.`, version check, one test prescription (section 2) |
| Weekly | The three log commands in section 5 |
| Monthly (1st) | Restore drill; record the result; check `Use%` |
| Every 90 days | Check the R2 tokens still work (`rclone lsf`), and that two-factor login is on |

## 10. Open items (2026-10-20)

- Lock test (section 4.2, step 11): not yet confirmed.
- First restore drill from the Mac (section 4.3): not yet run.
- 501 errors on upload: watch `~/backup.log` for `Attempt 3/3 failed`.
- Real restore (section 7): not yet rehearsed.

## Reference

| What | Where |
|---|---|
| First-time setup guide | `scripts/deploy/README.md` |
| Deploy script: pull | `scripts/deploy/02-deploy.sh:21-27` |
| Deploy script: keeps settings | `scripts/deploy/02-deploy.sh:53-55` |
| Deploy script: rebuild | `scripts/deploy/02-deploy.sh:57` |
| Deploy script: health wait | `scripts/deploy/02-deploy.sh:59-63` |
| Backup script: settings and defaults | `scripts/deploy/03-backup.sh:1-16` |
| Backup script: cron install | `scripts/deploy/03-backup.sh:18-25` |
| Backup script: online SQLite copy | `scripts/deploy/03-backup.sh:73-90` |
| Backup script: local retention | `scripts/deploy/03-backup.sh:98` |
| Backup script: off-site copy and size check | `scripts/deploy/03-backup.sh:107-116` |
| Restore drill and its defaults | `scripts/deploy/restore-drill.sh:1-12` (pass/fail lines `:65-84`) |
| Data volume name | `docker-compose.yml:4` |
| App user id 10001 | `Dockerfile:27` |
| Generic container runbook (Podman) | `docs/deploy/runbook.md` |

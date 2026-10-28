# VPS setup guide (Ubuntu 24.04, Docker, Caddy)

Plan: `docs/superpowers/plans/2026-10-18-hostinger-vps-deployment.md`. Existing runbook: `docs/deploy/runbook.md`.
This guide is first-time setup; it was run on the live server on 2026-10-18 to 2026-10-20. For day-to-day work (updates, backup checks,
restores, troubleshooting) use `docs/deploy/vps-operations.md`. Run each step yourself and read the output.

This guide uses the real values for this pilot: server `200.234.34.10`, address `gsr.lightday.online`, SSH key `~/.ssh/id_ed25519_dictdoc_vps`.
**Mac** = run on your laptop. **Server** = run inside an SSH session on the VPS.

```
Your Mac ──ssh──> VPS (200.234.34.10)
                   ├─ Caddy  (front door: HTTPS, certificate)
                   └─ App    (the dictation software, in a container)
Doctors ──https://gsr.lightday.online──> Caddy ──> App
```

## Three different keys (do not mix them up)

| Key | Made where | Used for | Where it goes |
|---|---|---|---|
| **SSH key** (`id_ed25519_dictdoc_vps`) | Mac, already done | You logging in to the server | Public half already added in Hostinger. **Do not make another.** |
| **Backup key** (`dictdoc-backup.key`, step 1) | Mac | Encrypting and opening backups | Only the PUBLIC text (`age1...`) goes on the server, in a file. Never added to Hostinger. The private file stays off the server. |
| **Deploy key** (step 5) | The server, by the script | The server downloading code from GitHub | Public half goes to GitHub (read-only). Never added to Hostinger. |

## Before you start
1. DNS: `dig +short gsr.lightday.online @1.1.1.1` must print `200.234.34.10`. The Cloudflare record must be grey ("DNS only"), not orange.

## Step 1. Make the backup key (Mac, once)
**What and why:** this makes two encryption keys. The public one locks backups and goes on the server. The private one unlocks them and stays off the server, so someone who breaks into the server cannot read old backups.
```
brew install age
age-keygen -o ~/dictdoc-backup.key
```
You should see `Public key: age1...`. Copy that line. Save `~/dictdoc-backup.key` in a password manager; if you lose it, backups cannot be restored.

## Step 2. Copy the scripts and run stage 1
**What and why:** `scp` copies files from your Mac to the server over an encrypted connection. `ssh` opens a terminal on the server.
`01-harden.sh` updates the system, makes a normal user `deploy`, turns on the firewall (only ports 22, 80, 443), installs `fail2ban` (blocks repeated login guesses), turns on automatic security updates and installs Docker.
A normal user is safer than `root`, because a typo as root can wreck the server.

**Mac**
```
cd /Users/narenlingala/Documents/workspace/work/Zebra/doctor-dic/doctor-dictation-main
scp -i ~/.ssh/id_ed25519_dictdoc_vps scripts/deploy/*.sh root@200.234.34.10:~/
ssh -i ~/.ssh/id_ed25519_dictdoc_vps root@200.234.34.10
```
Type `yes` at the host-key question, and your key passphrase if asked.

**Server**
```
bash 01-harden.sh
```
You should see "Stage 1 done".

## Step 3. Test the new login, then lock root out
**What and why:** first prove the `deploy` login works, then turn off root and password logins so only your key works.
If you lock first and the `deploy` login is broken, nobody gets in and you must use Hostinger's recovery console.

**Mac, second terminal**
```
ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10
```
You should get a prompt as `deploy`. If it fails, stop and fix it before continuing.

**Server, back in the root terminal, only if the test worked**
```
bash 01-harden.sh --lock-ssh
```
You should see "SSH locked". Close the root terminal; keep the `deploy` one.

## Step 4. Copy the scripts to the deploy user
**What and why:** root cannot log in now, and the next scripts must live in the `deploy` user's home folder.

**Mac**
```
scp -i ~/.ssh/id_ed25519_dictdoc_vps scripts/deploy/*.sh deploy@200.234.34.10:~/
ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10
```
`ls` on the server should list `02-deploy.sh` and `03-backup.sh`.

## Step 5. Deploy the app
**What and why:** `02-deploy.sh` does this in order:
1. **Deploy key (first run only):** makes a key pair on the server and prints the public half. You add it to GitHub as a **read-only** key, so the server can download the code but never change it.
2. **Download:** clones the `main` branch.
3. **DNS check:** warns if the address does not point to this server.
4. **Settings:** asks for the OpenAI key (typing is hidden), makes a random `SESSION_SECRET` (the key that signs login cookies) and writes `.env.production`, readable only by you.
5. **Start:** builds and starts two containers. The app listens only on the server's own loopback. Caddy is the only thing the internet reaches, and it gets the HTTPS certificate automatically.
6. **Health wait:** calls `https://gsr.lightday.online/health` until the app answers.

**Server**
```
bash 02-deploy.sh gsr.lightday.online
```
The first run stops after printing a line that starts `ssh-ed25519 ... dictdoc-vps-deploy`:
1. In GitHub open the repo, then Settings > Deploy keys > Add deploy key.
2. Paste that line. Leave "Allow write access" unticked. Save.
3. Run the same command again.

You should see a prompt for the OpenAI key, a long build (the first one downloads Chromium for PDFs), then "Healthy." and a table with `app` and `caddy` running.

## Step 6. Create the first clinic
**What and why:** the app keeps each clinic's data and logins separate. This makes the clinic `gsr` and its first user, and prints a temporary password **once**. The first sign-in forces a password change.

**Server**
```
cd ~/app
docker compose --env-file .env.production exec app python -m doctor_dictation.admin create-clinic --slug gsr --name "<Clinic name>" --first-user <username>
```
Replace `<Clinic name>` and `<username>` first. Copy the password before closing the window.

## Step 7. Test in the browser
**What and why:** this proves the whole chain: domain name, certificate, app, speech, AI and PDFs.
Open `https://gsr.lightday.online`, sign in, change the password, then try:
- the date reads like `18 Oct 2026`
- dictate a **fake** patient, save, open the PDF
- upload a letterhead as a JPEG and as a PDF

Use fake data until the consent and data rules for real patients are decided: audio and text go to OpenAI.

## Step 8. Turn on backups
**What and why:** `03-backup.sh` takes a consistent copy of every database while the app runs, adds uploaded files, compresses and encrypts it with your public key and saves it in `~/backups`. `--install-cron` runs it every 6 hours (00:17, 06:17, 12:17, 18:17).
The server keeps 7 days of archives (`KEEP_DAYS`, default 7). Each run writes a `disk:` line to `~/backup.log`.
It refuses to write an unencrypted backup. A backup you have never opened is a hope, not a backup, so test a restore.

**Server**
```
mkdir -p ~/.config/backup
echo "age1...PASTE_YOUR_PUBLIC_KEY..." > ~/.config/backup/age-recipient.txt
bash 03-backup.sh
bash 03-backup.sh --install-cron
```
You should see `wrote /home/deploy/backups/data-...tar.gz.age`.

**Mac, restore test**
```
scp -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10:~/backups/data-*.age ~/Downloads/
age -d -i ~/dictdoc-backup.key ~/Downloads/data-<file>.age | tar tz
```
You should see `directory.db` and `clinics/gsr/app.db`. Do this before any real data goes in.
Next: Step 9 copies backups off the server.

## Step 9. Off-site copy to Cloudflare R2
**What and why:** a backup that sits on the server dies with the server. This step copies every archive to a Cloudflare R2 bucket. R2 only ever sees encrypted files; the private key stays on your Mac.

Two limits to know:
- The server deletes archives older than `KEEP_DAYS` (7 days) before it uploads. If uploads fail for longer than 7 days, an archive that never reached R2 can be deleted from the server. Act on a `/fail` alert or an `OFF-SITE COPY FAILED` line in `~/backup.log` within a week.
- The drill (Step 10) reads archive names in the Mac's time zone, but the names use the server's local time. The staleness warning can be off by the zone difference. It is a warning only.

**Cloudflare dashboard**
1. Open R2 > Create bucket. Name it `dictdoc-backups`. Choose a location hint (Asia-Pacific is nearest to India). Create it.
2. Open the bucket > Settings > Object lifecycle rules. Add a rule for the whole bucket: delete objects 90 days after upload.
3. On the same Settings page, find "Bucket lock rules". Add a rule for the whole bucket: retain 30 days. Check that the saved rule shows 30 days. If the page has no such section, stop and tell the developer.
4. Turn on two-factor login for the Cloudflare account (My Profile > Authentication). The lock protects against a stolen server, not a stolen Cloudflare login.
5. Open R2 > Manage API tokens > Create API token. Permission: Object Read & Write. Apply to: `dictdoc-backups` only. Name: `dictdoc-vps-backup`. Create.
6. Copy the Access Key ID, the Secret Access Key and the S3 endpoint (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`) into your password manager. The secret is shown once.
7. Create a second token: Object Read only, `dictdoc-backups` only, name `dictdoc-mac-restore`. Save its keys too.

**Healthchecks.io (optional)**

8. At healthchecks.io create a check. Schedule: period 6 hours, grace 1 hour. Copy its ping URL.

**Server** (`ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10`)

9. Copy the new script from the Mac first (run on the Mac, in the repo folder): `scp -i ~/.ssh/id_ed25519_dictdoc_vps scripts/deploy/03-backup.sh deploy@200.234.34.10:~/`
10. Install rclone: `sudo apt-get update && sudo apt-get install -y rclone`
11. Check that rclone knows R2: `rclone version` (1.59 or newer), then `rclone help backend s3 | grep -i cloudflare` (prints a line).
12. Make the config file, private from the start: `mkdir -p ~/.config/rclone && [ -f ~/.config/rclone/rclone.conf ] || install -m 600 /dev/null ~/.config/rclone/rclone.conf`
13. Open it: `nano ~/.config/rclone/rclone.conf`. Paste the block below with your three values. The first line must be `[r2]` and no line may start with spaces; without the header `rclone listremotes` prints `DEFAULT:` and every command fails with "didn't find section in config file". Save with Ctrl-O, Enter, Ctrl-X. (Typing keys in an editor keeps them out of shell history.)

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

14. Test the login: `rclone listremotes` prints `r2:`, and `rclone lsf r2:dictdoc-backups` prints nothing and no error.
15. Make the backup settings file: `install -m 600 /dev/null ~/.config/backup/backup.env && nano ~/.config/backup/backup.env`
16. Put these two lines in it (leave out the `HC_PING_URL` line if you skipped step 8):

```
RCLONE_REMOTE=r2:dictdoc-backups
HC_PING_URL=https://hc-ping.com/<your-uuid>
```

17. Run one backup now: `bash ~/03-backup.sh`. The output has a `disk:` line (size, used and free of the backups disk, and the archive size). The last line reads `copied off-site to r2:dictdoc-backups: data-... (... bytes, verified)`.
18. Replace the nightly job: `bash ~/03-backup.sh --install-cron`
19. Confirm: `crontab -l` shows one line starting `17 */6 * * *` and no `17 2` line.
20. Test the lock: `rclone deletefile r2:dictdoc-backups/<the file from step 17>`. It must fail with an access or lock error. If it succeeds, the lock is not on; repeat step 3.
21. Check the alert (if step 8 done): healthchecks.io shows the check green within a minute.
22. Next day, check the disk log: `grep 'disk:' ~/backup.log | tail -n 4`. You see four lines, one per run. The `Use%` column stays well under 80%.

## Step 10. Monthly restore drill (Mac)
**What and why:** this fetches the newest archive from R2, decrypts it with your private key and checks every database. Run it on the first of each month. A backup you have never restored is a hope, not a backup.

1. Install tools once: `brew install rclone age`
2. Make the rclone config once: `mkdir -p ~/.config/rclone && [ -f ~/.config/rclone/rclone.conf ] || install -m 600 /dev/null ~/.config/rclone/rclone.conf`
3. Open it with `nano ~/.config/rclone/rclone.conf` and add this block, with the `dictdoc-mac-restore` keys:

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

4. Run the drill from the repo folder: `bash scripts/deploy/restore-drill.sh`
5. Read the result. Each database line says `: ok` (the clinic lines then show counts, and the counts look right). The last line is `Drill passed`. A `WARNING: newest backup is ...` line means the off-site copy is stale.
6. Write the date and result in `docs/working/2026-10-18-deployment/README.md` under open item 2.
7. On the server, check the disk trend: `grep 'disk:' ~/backup.log | tail -n 30`. If `Use%` passes 70%, tell the developer.

The drill defaults: `RESTORE_REMOTE=r2-read:dictdoc-backups`, `AGE_KEY=~/dictdoc-backup.key`, `MAX_AGE_HOURS=12`. Set any of them before the command if yours differ. `--file <archive.age>` checks a file you already downloaded.

## If something goes wrong
- **"Permission denied (publickey)":** wrong key file, or the key is not on the server.
- **"HTTPS will fail until DNS matches":** `dig +short gsr.lightday.online @1.1.1.1` must print `200.234.34.10`, and the Cloudflare record must be grey.
- **No "Healthy." in step 5:** `cd ~/app && docker compose --env-file .env.production logs caddy --tail 30`.
- **Never paste** the OpenAI key, a private key or `.env.production` into chat or tickets.

## Later
- **Update, backups, restore, troubleshooting:** `docs/deploy/vps-operations.md`.
- `01-harden.sh --lock-ssh` writes `/etc/ssh/sshd_config.d/00-hardening.conf`; the `00-` name matters because sshd keeps the first value it reads.
- The `deploy` user has passwordless sudo and Docker access (both root-equivalent), protected only by your SSH key and passphrase.

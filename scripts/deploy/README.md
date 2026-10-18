# VPS setup guide (Ubuntu 24.04, Docker, Caddy)

Plan: `docs/superpowers/plans/2026-10-18-hostinger-vps-deployment.md`. Existing runbook: `docs/deploy/runbook.md`.
The scripts have not been run on a real server yet: run each step yourself and read the output.

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
**What and why:** `03-backup.sh` takes a consistent copy of every database while the app runs, adds uploaded files, compresses and encrypts it with your public key and saves it in `~/backups`, keeping 14 days. `--install-cron` runs it nightly at 02:17.
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
**Gap:** backups stay on the same server until copied off, so a lost server loses them too. Copy them to your Mac regularly, or set `RCLONE_REMOTE` (needs rclone) for an off-site copy.

## If something goes wrong
- **"Permission denied (publickey)":** wrong key file, or the key is not on the server.
- **"HTTPS will fail until DNS matches":** `dig +short gsr.lightday.online @1.1.1.1` must print `200.234.34.10`, and the Cloudflare record must be grey.
- **No "Healthy." in step 5:** `cd ~/app && docker compose --env-file .env.production logs caddy --tail 30`.
- **Never paste** the OpenAI key, a private key or `.env.production` into chat or tickets.

## Later
- **Update:** back up first, then `cd ~/app && git pull && docker compose --env-file .env.production up -d --build`.
- `01-harden.sh --lock-ssh` writes `/etc/ssh/sshd_config.d/00-hardening.conf`; the `00-` name matters because sshd keeps the first value it reads.
- The `deploy` user has passwordless sudo and Docker access (both root-equivalent), protected only by your SSH key and passphrase.

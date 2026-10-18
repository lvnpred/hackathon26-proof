# VPS setup scripts (Ubuntu 24.04, Docker, Caddy)

Plan: `docs/superpowers/plans/2026-10-18-hostinger-vps-deployment.md`. Existing runbook: `docs/deploy/runbook.md`.
Not yet run on a real server: run each step yourself and read the output.

Replace `<ip>` with the server IP and `<domain>` with the address doctors will open (for example `app.example.pro`).

## 0. Before the scripts
1. DNS: add an `A` record for `<domain>` pointing to `<ip>` (at your registrar). Wait until `dig +short <domain>` prints the IP.
2. On your Mac, make the backup key once. Keep the private file in a password manager, never on the server:
   `brew install age && age-keygen -o ~/dictdoc-backup.key` (it prints `Public key: age1...`).

## 1. Harden the server (as root, about 5 minutes)
```
scp -i ~/.ssh/id_ed25519_dictdoc_vps scripts/deploy/*.sh root@<ip>:~/
ssh -i ~/.ssh/id_ed25519_dictdoc_vps root@<ip>
bash 01-harden.sh
```
Keep that terminal open. In a second terminal check the new login works:
`ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@<ip>`. Only then, in the root terminal: `bash 01-harden.sh --lock-ssh`.

## 2. Deploy (as `deploy`)
```
ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@<ip>
bash 02-deploy.sh <domain>
```
The first run prints a deploy key. Add it in GitHub (repo Settings > Deploy keys, read-only), then run the same command again.
It asks for the OpenAI key (hidden), generates `SESSION_SECRET`, writes `.env.production` (mode 600), builds, starts, and waits for `https://<domain>/health`.
Then create the first clinic with the command it prints.

## 3. Backups (as `deploy`)
```
mkdir -p ~/.config/backup && echo "age1...your public key..." > ~/.config/backup/age-recipient.txt
bash 03-backup.sh              # one backup now, written to ~/backups (encrypted)
bash 03-backup.sh --install-cron
```
The script refuses to write an unencrypted backup. Copy backups off the server (set `RCLONE_REMOTE`, or pull them to your Mac with `scp`).
**Restore drill (do it once before real data):** copy one `.age` file to your Mac, then
`age -d -i ~/dictdoc-backup.key data-<date>.tar.gz.age | tar tz` lists the files. To restore on the server: stop `app`,
extract into the `doctor-dictation_data` volume, start `app`, and sign in.

## Notes
- `01-harden.sh --lock-ssh` writes `/etc/ssh/sshd_config.d/00-hardening.conf`; the `00-` name matters because sshd keeps the first value it reads.
- The `deploy` user has passwordless sudo and Docker access (both root-equivalent), protected only by your SSH key and passphrase.
- Update later: `cd ~/app && git pull && docker compose --env-file .env.production up -d --build`, take a backup first.

# Updating the live VPS

**Summary:** to put the latest `main` on the live site, take a backup, run the deploy script, check the version, then try one prescription in the browser. It takes about 10 minutes. The site is down for a few seconds during the rebuild, so update outside clinic hours.

| | |
|---|---|
| Site | https://gsr.lightday.online |
| Server | `deploy@200.234.34.10` (Hostinger KVM 2) |
| SSH key (Mac) | `~/.ssh/id_ed25519_dictdoc_vps` |
| App folder (server) | `~/app` |
| Settings (server) | `~/app/.env.production` (the update never changes it) |

## Steps

**On the Mac, log in to the server:**
```
ssh -i ~/.ssh/id_ed25519_dictdoc_vps deploy@200.234.34.10
```

**1. Back up first.**
```
bash ~/03-backup.sh
ls -lt ~/backups | head -3
```
The newest archive should be from a minute ago.

**2. Pull the new code and rebuild.**
```
bash ~/02-deploy.sh gsr.lightday.online
```
The script takes `main` from GitHub (fast-forward only), keeps `.env.production` as it is, rebuilds the containers and waits for the health check. It ends with `Healthy.` and a table with `app` and `caddy` running.

**3. Check the version.**
```
git -C ~/app log -1 --oneline
```
It must show the same commit as `origin/main` on GitHub.

**4. Test in the browser** (https://gsr.lightday.online):
1. Log in.
2. Dictate one short prescription.
3. Confirm each flagged medicine, then Save.
4. Print it, and check the medicine names, the section headings and the footer.
5. Reopen it from Today, and check the confirmed rows do not ask again.

## Optional settings

| Setting | Why | How |
|---|---|---|
| `OWNER_USERNAMES=<your username>` | Opens the owner screen for reviewing clinic list changes. Without it, that screen answers 404. | Add the line to `~/app/.env.production`, then `cd ~/app && docker compose --env-file .env.production up -d` |
| New backup script | Off-site copies to Cloudflare R2 and the monthly restore drill | `scripts/deploy/README.md`, Steps 9 and 10 |

## If something goes wrong

Go back to the previous version (replace `<old-commit>` with the commit step 3 showed before the update):
```
cd ~/app && git checkout <old-commit> && docker compose --env-file .env.production up -d --build
```
A newer version can add database tables. The older code has not been tested against them. If the older version misbehaves, restore the backup from step 1 (`scripts/deploy/README.md`, restore test).

Logs: `cd ~/app && docker compose --env-file .env.production logs --tail 100 app`

## Reference

- Deploy script: `scripts/deploy/02-deploy.sh` (pull `:21-27`, keeps settings `:53-55`, rebuild `:57`, health wait `:59-63`)
- Full setup guide: `scripts/deploy/README.md`

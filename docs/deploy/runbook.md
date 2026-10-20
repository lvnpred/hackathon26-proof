# Deployment runbook (container + HTTPS)

One host, two containers: `app` (the service) and `caddy` (HTTPS, request-size limits). All state is the `data`
volume (`directory.db` and `clinics/<slug>/`). Commands work with Podman (`podman compose`) or Docker
(`docker compose`); examples use `podman`. Run from the repo root. Always pass `--env-file`.

For the Hostinger VPS pilot, follow `scripts/deploy/README.md` (hardening, deploy and encrypted-backup scripts) and see
`docs/working/2026-10-18-deployment/README.md` for what is live and what is still open. This runbook stays the generic
reference (it uses Podman examples and a stop-the-app backup; the scripts use Docker and an online backup).

Not covered here (see the pending list): CORS allow-list and security headers, log monitoring, an audit viewer.

## 1. Decide first
- Host: Linux, 2 vCPU and 2 GB minimum (4 GB comfortable), public IP, TCP 80/443 and UDP 443 open.
- Domain and who adds its A record; who receives the first sign-in details and over which channel.
- OpenAI key and spending limit; `LLM_VISION_MODEL` if the main model cannot read images.
- Server timezone (OP numbers restart each local midnight). Medical-data consent, retention and breach handling.

## 2. First start
```bash
git clone <repo-url> doctor-dictation && cd doctor-dictation
cp .env.production.example .env.production && chmod 600 .env.production
python3 -c "import secrets; print(secrets.token_urlsafe(48))"      # paste as SESSION_SECRET
# edit SITE_ADDRESS, SESSION_SECRET, OPENAI_API_KEY
grep -c REPLACE_ME .env.production                                  # must print 0
git check-ignore .env.production                                    # must print the path
podman compose --env-file .env.production up -d --build
podman compose --env-file .env.production ps                        # app: healthy
podman compose --env-file .env.production logs caddy | grep -i "certificate obtained"
```

## 3. First clinic and user
```bash
podman compose --env-file .env.production exec app \
  python -m doctor_dictation.admin create-clinic --slug rao --name "Rao Clinic" --first-user dr.rao
```
The temporary password prints once. The first sign-in forces a new one. More users: `create-user`; forgotten password:
`reset-password` (see the README, "Multi-clinic sign-in").
Check: `curl -s -o /dev/null -w "%{http_code}\n" https://<domain>/api/v1/profile` prints 401; `/health` prints 200.
In a browser: sign in, change the password, dictate one fake patient (the mic needs HTTPS), save, open the PDF.

## 4. Back up and restore (app stopped for a clean SQLite copy)
```bash
podman compose --env-file .env.production stop app
podman run --rm -v doctor-dictation_data:/data -v "$PWD":/backup docker.io/library/alpine \
  tar czf /backup/data-$(date +%F).tgz -C /data .
podman compose --env-file .env.production start app
# prove the backup opens (use sqlite3 in the image, any clinic):
mkdir -p /tmp/rt && tar xzf data-$(date +%F).tgz -C /tmp/rt && ls -R /tmp/rt | head
```
Copy the `.tgz` off the host. Restore: stop `app`, then
`podman run --rm -v doctor-dictation_data:/data -v "$PWD":/backup docker.io/library/alpine sh -c "rm -rf /data/* /data/.[!.]* ; tar xzf /backup/data-<date>.tgz -C /data"`, start `app`, repeat the checks in step 3.

## 5. Update or roll back
Update: back up (step 4), `podman tag doctor-dictation:local doctor-dictation:prev`, `git pull`,
`podman compose --env-file .env.production up -d --build`, repeat the step 3 checks.
Roll back: `APP_TAG=prev podman compose --env-file .env.production up -d --no-build app`; if the new version applied a
database migration, also restore the step 4 backup (migrations only go forward).

## 6. Settings that matter
- `SESSION_SECRET`: strong and private; changing it signs everyone out.
- The app trusts forwarded headers from any peer (`--forwarded-allow-ips='*'`) because its port is reachable only by
  Caddy and loopback. Never publish the app port on a public interface: login lockout is per username + client IP.
- `WEB_CONCURRENCY` = CPU cores; each worker holds its own Chromium (about 300 MiB).
- `DEMO_MODE` must stay unset.

## 7. Stop
Offline, data kept: `podman compose --env-file .env.production stop caddy app`. Remove everything including data
(irreversible, back up first): `podman compose --env-file .env.production down -v`.

## 8. Trying it locally with Podman (what was tested)
`podman machine init && podman machine start`, then use a throwaway env file with `SITE_ADDRESS=localhost`,
stub providers (`ALLOW_STUB_PROVIDERS=1`, `STT_CHAIN=stub`, `LLM_PROVIDER=stub`, `STUB_LLM_JSON=<a prescription>`) and
`HTTP_PORT=8080 HTTPS_PORT=8443 APP_LOCAL_PORT=18000` (rootless Podman cannot bind 80/443). Create a clinic as in
step 3, then:
`python tests/load/run_load.py --url http://127.0.0.1:18000 --container doctor-dictation-app-1 --user <u> --password <p> --new-password <permanent>`
(add `--insecure` with `https://localhost:8443`). Gate: no 5xx, p95 under 6 s, one PDF per save, flat memory.

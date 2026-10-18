#!/usr/bin/env bash
# Run as the deploy user:  bash 02-deploy.sh <domain> [git-ref]
# First run stops after printing a deploy key: add it to GitHub (repo Settings > Deploy keys, read-only), then run again.
set -euo pipefail
DOMAIN=${1:?usage: bash 02-deploy.sh <domain> [git-ref]}
REF=${2:-main}
REPO=${REPO:-git@github.com:lvnpred/doctor-dictation.git}
APP_DIR=${APP_DIR:-$HOME/app}
KEY=$HOME/.ssh/deploy_key
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"

docker info >/dev/null 2>&1 || { echo "Docker is not usable by this user; log out and in again after stage 1." >&2; exit 1; }

if [ ! -f "$KEY" ]; then
  ssh-keygen -t ed25519 -N "" -f "$KEY" -C "dictdoc-vps-deploy" >/dev/null
  echo "Add this PUBLIC key to GitHub as a read-only deploy key, then run this script again:"
  cat "$KEY.pub"
  exit 0
fi

if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --tags origin
else
  git clone "$REPO" "$APP_DIR"
fi
git -C "$APP_DIR" checkout "$REF"
[ "$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD)" = HEAD ] || git -C "$APP_DIR" pull --ff-only origin "$REF"
cd "$APP_DIR"

# The domain must already point at this server, or Caddy cannot get a certificate.
SERVER_IP=$(curl -4 -fsS https://api.ipify.org || true)
DNS_IP=$(getent ahostsv4 "$DOMAIN" | awk '{print $1; exit}' || true)
[ -n "$DNS_IP" ] && [ "$DNS_IP" = "$SERVER_IP" ] || echo "WARNING: $DOMAIN resolves to '${DNS_IP:-nothing}', this server is '$SERVER_IP'. HTTPS will fail until DNS matches." >&2

if [ ! -f .env.production ]; then
  read -rsp "OpenAI API key (hidden, input is not echoed): " OPENAI_API_KEY; echo
  [ -n "$OPENAI_API_KEY" ] || { echo "A key is required." >&2; exit 1; }
  SESSION_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  export DOMAIN OPENAI_API_KEY SESSION_SECRET
  python3 - <<'PY'
import os
vals = {"SITE_ADDRESS": os.environ["DOMAIN"], "SESSION_SECRET": os.environ["SESSION_SECRET"],
        "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"]}
out = []
for line in open(".env.production.example"):
    k = line.split("=", 1)[0]
    out.append(f"{k}={vals[k]}\n" if k in vals else line)
open(".env.production", "w").write("".join(out))
PY
  chmod 600 .env.production
  unset OPENAI_API_KEY SESSION_SECRET
  echo "Created .env.production (mode 600)."
else
  echo ".env.production already exists; leaving it as it is."
fi

docker compose --env-file .env.production up -d --build

echo "Waiting for https://$DOMAIN/health (up to 5 minutes)..."
for _ in $(seq 1 60); do
  curl -fsS "https://$DOMAIN/health" >/dev/null 2>&1 && { echo "Healthy."; break; }
  sleep 5
done
docker compose --env-file .env.production ps
echo
echo "Create the first clinic:"
echo "  docker compose --env-file .env.production exec app python -m doctor_dictation.admin create-clinic --slug <slug> --name \"<Clinic name>\" --first-user <username>"

#!/usr/bin/env bash
# Nightly encrypted backup of every database and uploaded file under /data, taken while the app runs.
#   bash 03-backup.sh                 one backup now
#   bash 03-backup.sh --install-cron  run it every night at 02:17
# Needs an age PUBLIC key in $AGE_RECIPIENT_FILE (default ~/.config/backup/age-recipient.txt). Keep the PRIVATE key off this server.
# Optional off-site copy: set RCLONE_REMOTE (for example "mybucket:dictdoc") and install and configure rclone.
set -euo pipefail
APP_DIR=${APP_DIR:-$HOME/app}
OUT=${BACKUP_DIR:-$HOME/backups}
KEEP_DAYS=${KEEP_DAYS:-14}
RECIPIENT=${AGE_RECIPIENT_FILE:-$HOME/.config/backup/age-recipient.txt}

if [ "${1:-}" = "--install-cron" ]; then
  line="17 2 * * * $(readlink -f "$0") >> $HOME/backup.log 2>&1"
  ( crontab -l 2>/dev/null | grep -vF "$(readlink -f "$0")" ; echo "$line" ) | crontab -
  echo "Installed: $line"; exit 0
fi

[ -s "$RECIPIENT" ] || { echo "No age public key at $RECIPIENT; refusing to write an unencrypted backup." >&2; exit 1; }
mkdir -p "$OUT"; chmod 700 "$OUT"
cd "$APP_DIR"
file="$OUT/data-$(date +%F-%H%M).tar.gz.age"

# SQLite's online backup API gives a consistent copy of each .db even while the app writes to it.
docker compose --env-file .env.production exec -T app python -c '
import os, sqlite3, sys, tarfile, tempfile
root = "/data"
with tempfile.TemporaryDirectory() as tmp, tarfile.open(fileobj=sys.stdout.buffer, mode="w|gz") as tar:
    for dirpath, _, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(("-wal", "-shm", "-journal")):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, root)
            if name.endswith(".db"):
                copy = os.path.join(tmp, rel.replace("/", "__"))
                src, dst = sqlite3.connect(path), sqlite3.connect(copy)
                src.backup(dst); dst.close(); src.close()
                tar.add(copy, arcname=rel)
            else:
                tar.add(path, arcname=rel)
' | age -R "$RECIPIENT" > "$file"

size=$(stat -c %s "$file")
[ "$size" -gt 1024 ] || { echo "Backup looks empty ($size bytes): $file" >&2; rm -f "$file"; exit 1; }
echo "$(date -Is) wrote $file ($size bytes)"

find "$OUT" -name 'data-*.tar.gz.age' -mtime +"$KEEP_DAYS" -delete
if [ -n "${RCLONE_REMOTE:-}" ]; then
  rclone copy "$file" "$RCLONE_REMOTE" && echo "copied off-site to $RCLONE_REMOTE"
fi

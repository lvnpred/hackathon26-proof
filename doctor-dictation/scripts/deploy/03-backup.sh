#!/usr/bin/env bash
# Encrypted backup of every database and uploaded file under /data, taken while the app runs. Runs every 6 hours; keeps 7 days locally.
#   bash 03-backup.sh                 one backup now
#   bash 03-backup.sh --install-cron  run it every 6 hours at minute 17
# Needs an age PUBLIC key in $AGE_RECIPIENT_FILE (default ~/.config/backup/age-recipient.txt). Keep the PRIVATE key off this server.
# Optional off-site copy: set RCLONE_REMOTE (for example "mybucket:dictdoc") and install and configure rclone.
# Settings file (default ~/.config/backup/backup.env, override with BACKUP_ENV): plain KEY=value lines, read before the defaults below.
# Keys: RCLONE_REMOTE (off-site bucket), KEEP_DAYS (local retention, default 7) and HC_PING_URL (optional healthchecks.io check URL).
set -euo pipefail
BACKUP_ENV=${BACKUP_ENV:-$HOME/.config/backup/backup.env}
if [ -f "$BACKUP_ENV" ] && [ -r "$BACKUP_ENV" ]; then set -a; . "$BACKUP_ENV"; set +a; fi
RCLONE_REMOTE=${RCLONE_REMOTE:-}; RCLONE_REMOTE=${RCLONE_REMOTE%/}   # a trailing slash would make a double slash in remote paths
APP_DIR=${APP_DIR:-$HOME/app}
OUT=${BACKUP_DIR:-$HOME/backups}
KEEP_DAYS=${KEEP_DAYS:-7}
RECIPIENT=${AGE_RECIPIENT_FILE:-$HOME/.config/backup/age-recipient.txt}

if [ "${1:-}" = "--install-cron" ]; then
  self=$(readlink -f "$0")
  line="17 */6 * * * $self >> $HOME/backup.log 2>&1"
  # "|| true": with no crontab yet, crontab -l prints nothing and grep -v exits 1, which set -e would turn into a silent stop.
  { crontab -l 2>/dev/null | grep -vF "$self" || true; echo "$line"; } | crontab -
  crontab -l | grep -qF "$self" || { echo "Cron install failed: the job is not in crontab -l." >&2; exit 1; }
  echo "Installed: $line"; exit 0
fi

# One run at a time: a slow run must not overlap the next cron start. Skipped when flock is not installed.
if command -v flock >/dev/null 2>&1; then
  exec 9>"$HOME/.backup.lock"
  flock -n 9 || { echo "another backup is running; skipped"; exit 0; }
fi

[ -s "$RECIPIENT" ] || { echo "No age public key at $RECIPIENT; refusing to write an unencrypted backup." >&2; exit 1; }
mkdir -p "$OUT"; chmod 700 "$OUT"
cd "$APP_DIR"
file="$OUT/data-$(date +%F-%H%M).tar.gz.age"
tmp="$file.part"   # written under this name and renamed only after it succeeds, so a final name always means a complete backup
stage=local   # becomes "offsite" once the local file is final; after that the off-site step reports its own failures
reported=0   # set by offsite_fail so the trap does not print a second failure line
hc_ping() {   # $1 = "" (success) or "/fail"; never fails the run
  [ -n "${HC_PING_URL:-}" ] || return 0
  curl -fsS -m 10 --retry 3 -o /dev/null "$HC_PING_URL$1" || echo "warning: healthchecks ping failed" >&2
  return 0
}
log_disk() {   # one line per run: disk usage of the backup folder and the new archive size
  local row
  row=$(df -hP "$OUT" 2>/dev/null | awk 'NR==2{print $1, $2, $3, $4, $5, $6}') || row=""
  echo "$(date +%Y-%m-%dT%H:%M:%S%z) disk: ${row:-unknown}; archive $size bytes"
}
on_exit() {
  local rc=$?
  rm -f "$tmp"
  [ "$rc" -ne 0 ] || return 0
  hc_ping /fail
  if [ "$stage" = local ]; then
    echo "$(date +%Y-%m-%dT%H:%M:%S%z) BACKUP FAILED (exit $rc); no file kept" >&2
  elif [ "$reported" -eq 0 ]; then
    echo "$(date +%Y-%m-%dT%H:%M:%S%z) POST-BACKUP STEP FAILED (exit $rc); local copy kept at $file" >&2
  fi
}
trap on_exit EXIT
find "$OUT" -name '*.part' -mmin +60 -delete   # leftovers from a run that was killed outright

# Refuse to start when the disk cannot hold another archive (twice the newest one, and at least 1 GiB).
last=0; newest=$(ls -t "$OUT"/data-*.tar.gz.age 2>/dev/null | head -1 || true)
[ -z "$newest" ] || last=$(stat -c %s "$newest")
free=$(df -Pk "$OUT" | awk 'NR==2{printf "%.0f\n", $4*1024}')
if [ "$free" -lt $((2 * last)) ] || [ "$free" -lt 1073741824 ]; then
  echo "low disk: $free bytes free, last backup $last bytes" >&2; exit 1
fi

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
' | age -R "$RECIPIENT" > "$tmp"

size=$(stat -c %s "$tmp")
[ "$size" -gt 1024 ] || { echo "Backup looks empty ($size bytes); not keeping it." >&2; exit 1; }
mv "$tmp" "$file"
stage=offsite
echo "$(date +%Y-%m-%dT%H:%M:%S%z) wrote $file ($size bytes)"

find "$OUT" -name 'data-*.tar.gz.age' -mtime +"$KEEP_DAYS" -delete
log_disk

offsite_fail() {
  reported=1
  echo "$(date +%Y-%m-%dT%H:%M:%S%z) OFF-SITE COPY FAILED ($1); local copy kept at $file" >&2
  exit 1
}
# --ignore-existing never overwrites a remote object, so a bucket lock cannot block it, and every earlier missed archive goes up too.
offsite_copy() {
  command -v rclone >/dev/null 2>&1 || offsite_fail "rclone not installed"
  local rc=0 remote
  rclone copy "$OUT" "$RCLONE_REMOTE" --include 'data-*.tar.gz.age' --ignore-existing || rc=$?
  [ "$rc" -eq 0 ] || offsite_fail "rclone copy exit $rc"
  remote=$(rclone lsl "$RCLONE_REMOTE/$(basename "$file")" | awk 'NR==1{print $1}') || remote=""
  [ "$remote" = "$size" ] || offsite_fail "size mismatch local=$size remote=${remote:-none}"
  echo "$(date +%Y-%m-%dT%H:%M:%S%z) copied off-site to $RCLONE_REMOTE: $(basename "$file") ($size bytes, verified)"
}
if [ -n "$RCLONE_REMOTE" ]; then offsite_copy; else echo "off-site copy: skipped (RCLONE_REMOTE not set)" >&2; fi
hc_ping ""

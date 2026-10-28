#!/usr/bin/env bash
# Restore drill (run monthly on the owner's Mac): fetch the newest off-site backup, decrypt it,
# and check every database. Usage: bash restore-drill.sh [--file <archive.age>]
# Env: RESTORE_REMOTE (default r2-read:dictdoc-backups), AGE_KEY (default ~/dictdoc-backup.key), MAX_AGE_HOURS (default 12).
# Exit 0 only when every database passes. The decrypted data is patient data: it lives in a private
# temp folder that is removed on success, failure and Ctrl-C. Nothing is copied elsewhere.
set -euo pipefail
umask 077

RESTORE_REMOTE=${RESTORE_REMOTE:-r2-read:dictdoc-backups}
AGE_KEY=${AGE_KEY:-$HOME/dictdoc-backup.key}
MAX_AGE_HOURS=${MAX_AGE_HOURS:-12}
archive=""

while [ $# -gt 0 ]; do
  case "$1" in
    --file) [ $# -ge 2 ] || { echo "--file needs a path" >&2; exit 2; }; archive=$2; shift 2;;
    *) echo "usage: $0 [--file <archive.age>]" >&2; exit 2;;
  esac
done

need="age sqlite3 tar"; [ -n "$archive" ] || need="$need rclone"
for c in $need; do command -v "$c" >/dev/null 2>&1 || { echo "ERROR: $c is not installed" >&2; exit 1; }; done
[ -f "$AGE_KEY" ] || { echo "ERROR: AGE_KEY file not found: $AGE_KEY" >&2; exit 1; }

work=$(mktemp -d "${TMPDIR:-/tmp}/restore-drill.XXXXXX")   # explicit template: BSD mktemp -d ignores TMPDIR otherwise
trap 'rm -rf "$work"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
mkdir "$work/data"

if [ -z "$archive" ]; then
  name=$(rclone lsf "$RESTORE_REMOTE" --include 'data-*.tar.gz.age' | sort | tail -n1)   # names sort by time (data-%F-%H%M)
  [ -n "$name" ] || { echo "ERROR: no backup found in $RESTORE_REMOTE" >&2; exit 1; }
  rclone copyto "$RESTORE_REMOTE/$name" "$work/$name"
  archive=$work/$name
fi
base=$(basename "$archive")
echo "Archive: $base"

# Staleness: parse data-YYYY-MM-DD-HHMM; GNU date first, then BSD date. Skipped if the name does not parse.
ts=$(printf '%s' "$base" | sed -n 's/^data-\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\}\)-\([0-9]\{2\}\)\([0-9]\{2\}\).*/\1 \2:\3/p')
epoch=""
if [ -n "$ts" ]; then
  epoch=$(date -d "$ts" +%s 2>/dev/null) || epoch=$(date -j -f '%Y-%m-%d %H:%M' "$ts" +%s 2>/dev/null) || epoch=""
fi
if [ -n "$epoch" ]; then
  age_h=$(( ( $(date +%s) - epoch ) / 3600 ))
  if [ "$age_h" -gt "$MAX_AGE_HOURS" ]; then
    echo "WARNING: newest backup is ${age_h}h old (limit ${MAX_AGE_HOURS}h)"
  fi
fi

age -d -i "$AGE_KEY" "$archive" | tar xzf - -C "$work/data"

fail=0
# A backed-up WAL database keeps its WAL flag but the archive has no -wal/-shm files, so a plain -readonly open fails
# ("unable to open database file"). An immutable URI opens the single file as it is. Percent-encode the path for the URI.
uri() { printf 'file:%s?immutable=1' "$(printf '%s' "$1" | sed -e 's/%/%25/g' -e 's/ /%20/g' -e 's/?/%3F/g' -e 's/#/%23/g')"; }
check_db() {   # path relative to $work/data
  local rel=$1 res
  res=$(sqlite3 -readonly "$(uri "$work/data/$rel")" 'PRAGMA integrity_check;' 2>&1) || true
  [ "$res" = ok ]
}
if [ -f "$work/data/directory.db" ] && check_db directory.db; then echo "directory.db: ok"
else echo "directory.db: FAILED"; fail=1; fi

found=0
for db in "$work"/data/clinics/*/app.db; do
  [ -f "$db" ] || continue
  found=1
  rel=${db#"$work"/data/}; dir=$(dirname "$db")
  if check_db "$rel" \
     && docs=$(sqlite3 -readonly "$(uri "$db")" 'SELECT COUNT(*) FROM documents;' 2>/dev/null) \
     && formu=$(sqlite3 -readonly "$(uri "$db")" 'SELECT COUNT(*) FROM clinic_formulary;' 2>/dev/null); then
    pdfs=$(find "$dir/pdfs" -maxdepth 1 -name '*.pdf' 2>/dev/null | wc -l | tr -d ' ')
    echo "$rel: ok documents=$docs clinic_formulary=$formu pdfs=$pdfs"
  else
    echo "$rel: FAILED"; fail=1
  fi
done
[ "$found" = 1 ] || { echo "clinics/*/app.db: FAILED (none found)"; fail=1; }

if [ "$fail" = 0 ]; then echo "Drill passed"; else echo "Drill FAILED"; exit 1; fi

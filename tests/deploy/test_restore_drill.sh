#!/usr/bin/env bash
# Tests for scripts/deploy/restore-drill.sh using stand-in commands (tests/deploy/stubs). Run: bash tests/deploy/test_restore_drill.sh
cd "$(dirname "$0")/../.." || exit 1
ROOT=$PWD
SCRIPT=$ROOT/scripts/deploy/restore-drill.sh
STUBS=$ROOT/tests/deploy/stubs
SQLITE=/usr/bin/sqlite3
FAILS=0

setup() {
  T=$(mktemp -d)
  export HOME=$T/home FAKE_BUCKET=$T/bucket FAKE_RCLONE_LOG=$T/rclone.log TMPDIR=$T/tmp
  mkdir -p "$HOME" "$FAKE_BUCKET/bk" "$TMPDIR"
  : > "$FAKE_RCLONE_LOG"
  echo "AGE-SECRET-KEY-FAKE" > "$T/key"
  unset RESTORE_REMOTE AGE_KEY MAX_AGE_HOURS
  export RESTORE_REMOTE=fake:bk AGE_KEY=$T/key
  export PATH="$STUBS:/usr/bin:/bin"
}
run() { bash "$SCRIPT" "$@" >"$T/out" 2>&1; }
check() { local name=$1; shift
  if ( "$@" ); then echo "PASS $name"; else echo "FAIL $name"; FAILS=$((FAILS+1)); fi; }

# make_archive OUTFILE CLINIC [corrupt]: directory.db + clinics/CLINIC/{app.db,pdfs/encounter_1.pdf}; tar-gz'd (age stub is cat)
make_archive() {   # databases are WAL and copied with SQLite's online backup, exactly as 03-backup.sh does
  local out=$1 clinic=$2 corrupt=${3:-} d s; d=$(mktemp -d); s=$(mktemp -d)
  mkdir -p "$d/clinics/$clinic/pdfs"
  $SQLITE "$s/directory.db" 'PRAGMA journal_mode=WAL; CREATE TABLE clinics(slug TEXT); INSERT INTO clinics VALUES("'"$clinic"'");' >/dev/null
  $SQLITE "$s/directory.db" ".backup '$d/directory.db'"
  if [ -n "$corrupt" ]; then head -c 4096 /dev/urandom > "$d/clinics/$clinic/app.db"
  else $SQLITE "$s/app.db" 'PRAGMA journal_mode=WAL; CREATE TABLE documents(id INTEGER); INSERT INTO documents VALUES(1),(2);
    CREATE TABLE clinic_formulary(id INTEGER); INSERT INTO clinic_formulary VALUES(1);' >/dev/null
    $SQLITE "$s/app.db" ".backup '$d/clinics/$clinic/app.db'"; fi
  echo pdf > "$d/clinics/$clinic/pdfs/encounter_1.pdf"
  mkdir -p "$d/templates"; echo t > "$d/templates/x.txt"
  tar czf "$out" -C "$d" . ; rm -rf "$d" "$s"
}
fixture() { make_archive "$FAKE_BUCKET/bk/data-2026-10-19-0617.tar.gz.age" a "${1:-}"
            make_archive "$FAKE_BUCKET/bk/data-2026-10-18-0017.tar.gz.age" b; }

t_drill_picks_newest() { setup; fixture; run || return 1
  grep -q 'data-2026-10-19-0617.tar.gz.age' "$T/out" && grep -q 'clinics/a/app.db' "$T/out" && ! grep -q 'clinics/b/' "$T/out"; }
t_drill_ok() { setup; fixture; run || return 1
  grep -q '^directory.db: ok$' "$T/out" && grep -q '^clinics/a/app.db: ok documents=2 clinic_formulary=1 pdfs=1$' "$T/out" && grep -q 'Drill passed' "$T/out"; }
t_drill_corrupt_db_fails() { setup; fixture corrupt; run && return 1
  grep -q 'clinics/a/app.db: FAILED' "$T/out" && grep -q 'Drill FAILED' "$T/out"; }
t_drill_cleans_temp() { setup; fixture; run || return 1
  [ -z "$(ls -A "$TMPDIR")" ] || return 1
  fixture corrupt; run && return 1
  [ -z "$(ls -A "$TMPDIR")" ]; }
t_drill_cleans_temp_on_terminate() { setup; fixture
  mkdir -p "$T/slow"; ln -s "$STUBS"/* "$T/slow/"; rm "$T/slow/age"
  printf '#!/bin/sh\nsleep 30\n' > "$T/slow/age"; chmod +x "$T/slow/age"
  PATH="$T/slow:/usr/bin:/bin" bash "$SCRIPT" >"$T/out" 2>&1 & local pid=$!
  sleep 1; [ -n "$(ls -A "$TMPDIR")" ] || return 1; kill -TERM "$pid" 2>/dev/null; pkill -P "$pid" 2>/dev/null; wait "$pid" 2>/dev/null
  [ -z "$(ls -A "$TMPDIR")" ]; }
t_drill_local_file() { setup; make_archive "$T/local.tar.gz.age" a; : > "$FAKE_RCLONE_LOG"
  run --file "$T/local.tar.gz.age" || return 1
  [ ! -s "$FAKE_RCLONE_LOG" ] && grep -q 'Drill passed' "$T/out"; }
t_drill_stale_warns() { setup; make_archive "$FAKE_BUCKET/bk/data-2020-01-01-0000.tar.gz.age" a
  export MAX_AGE_HOURS=12; run || return 1
  grep -q 'WARNING: newest backup is' "$T/out"; }
t_drill_fresh_no_warning() { setup; make_archive "$FAKE_BUCKET/bk/data-$(date +%Y-%m-%d-%H%M).tar.gz.age" a
  run || return 1
  ! grep -q 'WARNING' "$T/out"; }
t_drill_missing_key_fails() { setup; fixture; rm "$T/key"; run && return 1; grep -q 'AGE_KEY' "$T/out"; }
t_drill_empty_remote_fails() { setup; run && return 1; grep -qi 'no backup' "$T/out"; }

for c in drill_picks_newest drill_ok drill_corrupt_db_fails drill_cleans_temp drill_cleans_temp_on_terminate \
  drill_local_file drill_stale_warns drill_fresh_no_warning drill_missing_key_fails drill_empty_remote_fails; do
  check "$c" "t_$c"
done
[ "$FAILS" -eq 0 ]

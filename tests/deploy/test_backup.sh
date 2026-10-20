#!/usr/bin/env bash
# Tests for scripts/deploy/03-backup.sh using stand-in commands (tests/deploy/stubs). Run: bash tests/deploy/test_backup.sh
cd "$(dirname "$0")/../.." || exit 1
ROOT=$PWD
SCRIPT=$ROOT/scripts/deploy/03-backup.sh
STUBS=$ROOT/tests/deploy/stubs
FAILS=0

age_file() { perl -e 'my $t = time - $ARGV[1]*86400; utime $t, $t, $ARGV[0]' "$1" "$2"; }

setup() {   # fresh sandbox with env wired to the stubs
  T=$(mktemp -d)
  export HOME=$T/home APP_DIR=$T/app BACKUP_DIR=$T/backups
  export FAKE_BUCKET=$T/bucket FAKE_RCLONE_LOG=$T/rclone.log FAKE_CURL_LOG=$T/curl.log FAKE_CRONTAB=$T/crontab
  mkdir -p "$HOME/.config/backup" "$APP_DIR" "$FAKE_BUCKET"
  echo "age1fakerecipient" > "$HOME/.config/backup/age-recipient.txt"
  : > "$FAKE_RCLONE_LOG"; : > "$FAKE_CURL_LOG"
  unset KEEP_DAYS RCLONE_REMOTE HC_PING_URL BACKUP_ENV FAKE_DOCKER_FAIL FAKE_RCLONE_FAIL FAKE_RCLONE_SHORT FAKE_CURL_FAIL FAKE_DF_KB FAKE_FLOCK_HELD
  export PATH="$STUBS:/usr/bin:/bin"
}
run() { bash "$SCRIPT" "$@" >"$T/out" 2>&1; }
check() { # name, command...
  local name=$1; shift
  if ( "$@" ) ; then echo "PASS $name"; else echo "FAIL $name"; FAILS=$((FAILS+1)); fi
}

t_cron_empty() { setup; run --install-cron || return 1
  [ "$(wc -l < "$FAKE_CRONTAB" | tr -d ' ')" = 1 ] &&
  grep -Eq '^17 \*/6 \* \* \* .*/03-backup.sh >> .*/backup.log 2>&1$' "$FAKE_CRONTAB"; }

t_cron_replaces_nightly() { setup
  printf '%s\n%s\n' "17 2 * * * $SCRIPT >> x 2>&1" "0 5 * * * other-job" > "$FAKE_CRONTAB"
  run --install-cron || return 1
  grep -qF "other-job" "$FAKE_CRONTAB" && ! grep -q '^17 2 ' "$FAKE_CRONTAB" &&
  [ "$(grep -c '^17 \*/6 ' "$FAKE_CRONTAB")" = 1 ]; }

t_cron_twice() { setup; run --install-cron && run --install-cron || return 1
  [ "$(grep -cF 03-backup.sh "$FAKE_CRONTAB")" = 1 ]; }

t_cron_env_reads_config() { setup
  echo "RCLONE_REMOTE=fake:bucket" > "$HOME/.config/backup/backup.env"
  env -i HOME="$HOME" PATH="$PATH" BACKUP_ENV="$HOME/.config/backup/backup.env" APP_DIR="$APP_DIR" BACKUP_DIR="$BACKUP_DIR" \
    FAKE_BUCKET="$FAKE_BUCKET" FAKE_RCLONE_LOG="$FAKE_RCLONE_LOG" FAKE_CURL_LOG="$FAKE_CURL_LOG" \
    bash "$SCRIPT" >"$T/out" 2>&1 || return 1
  grep -Eq "^copy $BACKUP_DIR fake:bucket --include data-\*\.tar\.gz\.age --ignore-existing\$" "$FAKE_RCLONE_LOG"; }

t_no_remote_local_only() { setup; run || return 1
  [ "$(ls "$BACKUP_DIR"/data-*.tar.gz.age | wc -l | tr -d ' ')" = 1 ] && [ ! -s "$FAKE_RCLONE_LOG" ]; }

t_keep_days_default_7() { setup; mkdir -p "$BACKUP_DIR"
  touch "$BACKUP_DIR/data-old.tar.gz.age" "$BACKUP_DIR/data-recent.tar.gz.age"
  age_file "$BACKUP_DIR/data-old.tar.gz.age" 8; age_file "$BACKUP_DIR/data-recent.tar.gz.age" 6
  run || return 1
  [ ! -e "$BACKUP_DIR/data-old.tar.gz.age" ] && [ -e "$BACKUP_DIR/data-recent.tar.gz.age" ]; }

local_file() { ls "$BACKUP_DIR"/data-*.tar.gz.age 2>/dev/null | sort | tail -1; }

t_upload_ok() { setup; export RCLONE_REMOTE=fake:bucket; run || return 1
  f=$(local_file); [ -e "$FAKE_BUCKET/bucket/$(basename "$f")" ] &&
  [ "$(wc -c < "$f" | tr -d ' ')" = "$(wc -c < "$FAKE_BUCKET/bucket/$(basename "$f")" | tr -d ' ')" ] && grep -q verified "$T/out"; }

t_upload_failure_keeps_local() { setup; export RCLONE_REMOTE=fake:bucket FAKE_RCLONE_FAIL=1
  run && return 1
  [ -e "$(local_file)" ] && grep -q 'OFF-SITE COPY FAILED' "$T/out" && grep -q 'local copy kept at' "$T/out" && ! grep -q 'no file kept' "$T/out" && ! grep -q 'POST-BACKUP STEP FAILED' "$T/out"; }

t_verify_mismatch_fails() { setup; export RCLONE_REMOTE=fake:bucket FAKE_RCLONE_SHORT=1
  run && return 1
  [ -e "$(local_file)" ] && grep -q 'size mismatch' "$T/out"; }

t_catch_up_uploads_missed_archive() { setup; export RCLONE_REMOTE=fake:bucket; mkdir -p "$BACKUP_DIR"
  head -c 2048 /dev/zero > "$BACKUP_DIR/data-2026-10-18-0217.tar.gz.age"
  run || return 1
  [ -e "$FAKE_BUCKET/bucket/data-2026-10-18-0217.tar.gz.age" ] && [ -e "$FAKE_BUCKET/bucket/$(basename "$(local_file)")" ] &&
  grep '^copy ' "$FAKE_RCLONE_LOG" | grep -q -- '--ignore-existing' &&
  grep '^copy ' "$FAKE_RCLONE_LOG" | grep -q -- '--include data-\*.tar.gz.age'; }

t_rclone_missing() { setup; export RCLONE_REMOTE=fake:bucket
  mkdir -p "$T/nor"; for x in "$STUBS"/*; do [ "$(basename "$x")" = rclone ] || ln -s "$x" "$T/nor/"; done
  PATH="$T/nor:/usr/bin:/bin"
  run && return 1
  [ -e "$(local_file)" ] && grep -q 'rclone not installed' "$T/out"; }

HC=https://hc.example/abc
t_hc_success() { setup; export HC_PING_URL=$HC; run || return 1; [ "$(cat "$FAKE_CURL_LOG")" = "$HC" ]; }
t_hc_fail_on_local_error() { setup; export HC_PING_URL=$HC FAKE_DOCKER_FAIL=1; run && return 1; [ "$(cat "$FAKE_CURL_LOG")" = "$HC/fail" ]; }
t_hc_fail_on_upload_error() { setup; export HC_PING_URL=$HC RCLONE_REMOTE=fake:bucket FAKE_RCLONE_FAIL=1; run && return 1
  [ "$(tail -1 "$FAKE_CURL_LOG")" = "$HC/fail" ] && ! grep -qx "$HC" "$FAKE_CURL_LOG"; }
t_hc_unset_no_curl() { setup; run || return 1; [ ! -s "$FAKE_CURL_LOG" ]; }
t_hc_curl_down_still_ok() { setup; export HC_PING_URL=$HC FAKE_CURL_FAIL=1; run || return 1; grep -q 'healthchecks ping failed' "$T/out"; }

t_low_disk_refuses() { setup; export HC_PING_URL=$HC FAKE_DF_KB=3; mkdir -p "$BACKUP_DIR"
  head -c 2048 /dev/zero > "$BACKUP_DIR/data-2026-10-18-0217.tar.gz.age"
  run && return 1
  [ "$(ls "$BACKUP_DIR"/data-*.tar.gz.age | wc -l | tr -d ' ')" = 1 ] && grep -q 'low disk' "$T/out" && [ "$(tail -1 "$FAKE_CURL_LOG")" = "$HC/fail" ]; }

t_logs_disk_usage() { setup; run || return 1
  [ "$(grep -c 'disk: ' "$T/out")" = 1 ] && grep -Eq 'disk: fakefs 100G 40G 60G 40% /fake; archive [0-9]+ bytes' "$T/out" &&
  [ "$(sed -n 's/.*archive \([0-9]*\) bytes.*/\1/p' "$T/out")" = "$(wc -c < "$(local_file)" | tr -d ' ')" ]; }

t_logs_disk_usage_with_upload() { setup; export RCLONE_REMOTE=fake:bucket; run || return 1
  grep -q 'disk: fakefs' "$T/out" && [ "$(grep -n 'disk: fakefs' "$T/out" | cut -d: -f1)" -lt "$(grep -n 'copied off-site' "$T/out" | cut -d: -f1)" ]; }

t_failure_after_local_final_is_reported() { setup; mkdir -p "$T/nof"; ln -s "$STUBS"/* "$T/nof/"
  printf '#!/bin/sh\ncase "$*" in *-mtime*) exit 1;; esac\nexec /usr/bin/find "$@"\n' > "$T/nof/find"; chmod +x "$T/nof/find"
  PATH="$T/nof:/usr/bin:/bin"
  run && return 1
  [ -e "$(local_file)" ] && grep -q 'POST-BACKUP STEP FAILED' "$T/out" && ! grep -q 'no file kept' "$T/out"; }

t_remote_trailing_slash_stripped() { setup; export RCLONE_REMOTE=fake:bucket/; run || return 1
  grep -q "^copy $BACKUP_DIR fake:bucket --include" "$FAKE_RCLONE_LOG" && ! grep -q 'bucket//' "$FAKE_RCLONE_LOG" && grep -q 'verified' "$T/out"; }

t_no_remote_logs_skip() { setup; run || return 1
  grep -q '^off-site copy: skipped (RCLONE_REMOTE not set)$' "$T/out"; }

t_lock_held_skips() { setup; export HC_PING_URL=$HC FAKE_FLOCK_HELD=1; run || return 1
  grep -q '^another backup is running; skipped$' "$T/out" && [ ! -s "$FAKE_CURL_LOG" ] && [ -z "$(ls "$BACKUP_DIR"/data-* 2>/dev/null)" ]; }

t_lock_free_runs() { setup; run || return 1
  [ -e "$HOME/.backup.lock" ] && [ "$(ls "$BACKUP_DIR"/data-*.tar.gz.age | wc -l | tr -d ' ')" = 1 ]; }

for c in cron_empty cron_replaces_nightly cron_twice cron_env_reads_config no_remote_local_only keep_days_default_7 \
  upload_ok upload_failure_keeps_local verify_mismatch_fails catch_up_uploads_missed_archive rclone_missing \
  hc_success hc_fail_on_local_error hc_fail_on_upload_error hc_unset_no_curl hc_curl_down_still_ok low_disk_refuses \
  logs_disk_usage logs_disk_usage_with_upload failure_after_local_final_is_reported remote_trailing_slash_stripped \
  no_remote_logs_skip lock_held_skips lock_free_runs; do
  check "$c" "t_$c"
done
[ "$FAILS" -eq 0 ]

#!/usr/bin/env bash
set -Eeuo pipefail
: "${NCS_REPO:?set NCS_REPO to the backend checkout}"
INTERVAL="${NCS_ADS_SYNC_INTERVAL_SECONDS:-30}"
SLEEP_PID=""
# Take the pending `sleep` down with us. `--stop` signals only this process,
# and once it is gone the child can no longer be found: MSYS re-parents it to
# init immediately, so it would linger up to INTERVAL seconds as a stray
# process. Backgrounding the sleep is what makes it addressable here.
on_stop() {
  [[ -z "$SLEEP_PID" ]] || kill "$SLEEP_PID" 2>/dev/null || true
  exit 0
}
trap on_stop TERM INT
while true; do
  "$NCS_REPO/scripts/shell/sync_ads_once.sh" || status=$?
  status="${status:-0}"
  if [[ "$status" != 0 && "$status" != 10 ]]; then
    printf '%s sync exit=%s\n' "$(date -Is)" "$status" >&2
  fi
  unset status
  sleep "$INTERVAL" &
  SLEEP_PID=$!
  wait "$SLEEP_PID" || true
  SLEEP_PID=""
done

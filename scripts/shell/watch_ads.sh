#!/usr/bin/env bash
set -Eeuo pipefail
: "${NCS_REPO:?set NCS_REPO to the backend checkout}"
INTERVAL="${NCS_ADS_SYNC_INTERVAL_SECONDS:-30}"
while true; do
  "$NCS_REPO/scripts/shell/sync_ads_once.sh" || status=$?
  status="${status:-0}"
  if [[ "$status" != 0 && "$status" != 10 ]]; then
    printf '%s sync exit=%s\n' "$(date -Is)" "$status" >&2
  fi
  unset status
  sleep "$INTERVAL"
done

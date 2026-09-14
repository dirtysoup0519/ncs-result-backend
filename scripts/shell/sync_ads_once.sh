#!/usr/bin/env bash
set -Eeuo pipefail

# Source NCS_ADS_SYNC_ENV before invoking this script. Secrets stay in the
# environment and are never stored in the repository.
: "${NCS_REPO:?set NCS_REPO to the backend checkout}"
: "${NCS_DATABASE_URL:?set NCS_DATABASE_URL to the VM MySQL URL}"
ROOT="${NCS_ADS_EXCHANGE_ROOT:-/data/ncs/ads_exchange}"
READY="$ROOT/ready"
ARCHIVE="$ROOT/archive"
REJECTED="$ROOT/rejected"
LOGS="$ROOT/logs"
LOCKS="$ROOT/locks"
MODEL_PACKAGE="${NCS_MODEL_PACKAGE:-}"
mkdir -p "$READY" "$ARCHIVE" "$REJECTED" "$LOGS" "$LOCKS"
exec 9>"$LOCKS/sync_ads.lock"
if ! flock -n 9; then exit 10; fi

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOGS/sync_ads.log"; }
package="$(find "$READY" -maxdepth 1 -type f \( -name '*.zip' -o -name '*.tar.gz' \) -printf '%T@ %p\n' | sort -n | head -n1 | cut -d' ' -f2- || true)"
if [[ -z "$package" ]]; then exit 0; fi
name="$(basename "$package")"
marker="$package.ready"
if [[ ! -f "$marker" ]]; then
  log "package is waiting for completion marker: $name"
  exit 20
fi
log "processing $name"
if ! python "$NCS_REPO/scripts/import_ads_v23.py" --package "$package" --database-url "$NCS_DATABASE_URL" --skip-initialize >>"$LOGS/$name.log" 2>&1; then
  log "import failed: $name"
  mv -- "$package" "$REJECTED/$name"
  mv -- "$marker" "$REJECTED/$(basename "$marker")" 2>/dev/null || true
  exit 50
fi

if [[ -n "$MODEL_PACKAGE" ]]; then
  if ! python "$NCS_REPO/scripts/run_load_prediction.py" --model-package "$MODEL_PACKAGE" --database-url "$NCS_DATABASE_URL" --horizon "${NCS_PREDICTION_HORIZON:-24}" >>"$LOGS/$name.log" 2>&1; then
    log "prediction failed after ADS publish; ADS remains published"
    mv -- "$package" "$ARCHIVE/$name"
    mv -- "$marker" "$ARCHIVE/$(basename "$marker")" 2>/dev/null || true
    exit 50
  fi
fi
mv -- "$package" "$ARCHIVE/$name"
mv -- "$marker" "$ARCHIVE/$(basename "$marker")" 2>/dev/null || true
log "completed $name"
exit 0

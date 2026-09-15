#!/usr/bin/env bash
set -Eeuo pipefail

# Source NCS_ADS_SYNC_ENV before invoking this script. Secrets stay in the
# environment and are never stored in the repository.
#
# Exit codes follow docs/ADS_v2.5自动同步与模型推理设计.md section 5.2:
#   0  success, or no eligible batch
#   10 lock held by another sync process
#   30 package data/contract problem -> rejected immediately
#   40 MySQL unavailable -> retried up to NCS_ADS_SYNC_MAX_ATTEMPTS
#   50 import/prediction internal error -> retried up to the attempt limit;
#      a package whose ADS import already succeeded is archived (not rejected)
#      once the prediction retry limit is exhausted
: "${NCS_REPO:?set NCS_REPO to the backend checkout}"
: "${NCS_DATABASE_URL:?set NCS_DATABASE_URL to the VM MySQL URL}"
ROOT="${NCS_ADS_EXCHANGE_ROOT:-/data/ncs/ads_exchange}"
READY="$ROOT/ready"
ARCHIVE="$ROOT/archive"
REJECTED="$ROOT/rejected"
LOGS="$ROOT/logs"
LOCKS="$ROOT/locks"
MODEL_PACKAGE="${NCS_MODEL_PACKAGE:-}"
PYTHON_BIN="${NCS_PYTHON_BIN:-python3}"
MAX_ATTEMPTS="${NCS_ADS_SYNC_MAX_ATTEMPTS:-3}"
TZ="${NCS_LOG_TZ:-Asia/Shanghai}"
export TZ
mkdir -p "$READY" "$ARCHIVE" "$REJECTED" "$LOGS" "$LOCKS"
exec 9>"$LOCKS/sync_ads.lock"
if ! flock -n 9; then exit 10; fi

log() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOGS/sync_ads.log"; }

if ! "$PYTHON_BIN" -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3, 11) else 1)' 2>/dev/null; then
  log "WARNING: $PYTHON_BIN is not Python 3.11/3.12; imports still run but final acceptance requires 3.11/3.12"
fi

# Select the oldest eligible batch. Files need a completion marker (.ready or
# .ready.predict); directories need _SUCCESS. Unfinished packages never block
# newer, already-completed ones.
package=""
oldest_ts=""
while IFS= read -r candidate; do
  if [[ -d "$candidate" ]]; then
    if [[ ! -f "$candidate/_SUCCESS" ]]; then continue; fi
  else
    case "$candidate" in
      *.zip|*.tar.gz)
        if [[ ! -f "$candidate.ready" && ! -f "$candidate.ready.predict" ]]; then continue; fi
        ;;
      *) continue ;;
    esac
  fi
  ts="$(stat -c '%Y' "$candidate")"
  if [[ -z "$oldest_ts" || "$ts" -lt "$oldest_ts" ]]; then
    package="$candidate"
    oldest_ts="$ts"
  fi
done < <(find "$READY" -mindepth 1 -maxdepth 1 \( -type f -o -type d \) -print)
if [[ -z "$package" ]]; then exit 0; fi

name="$(basename "$package")"
is_dir=0
if [[ -d "$package" ]]; then is_dir=1; fi
marker_path=""
if [[ -f "$package.ready" ]]; then marker_path="$package.ready"; fi
predict_mode=0
if [[ -f "$package.ready.predict" ]]; then marker_path="$package.ready.predict"; predict_mode=1; fi
attempts_file="$READY/$name.attempts"
attempts=0
if [[ -f "$attempts_file" ]]; then attempts="$(cat "$attempts_file")"; fi

log "processing $name (predict_mode=$predict_mode attempts=$attempts/$MAX_ATTEMPTS)"

work=""
if [[ "$is_dir" -eq 0 ]]; then
  work="$(mktemp -d "$ROOT/work.XXXXXX")"
  cleanup() { rm -rf -- "$work"; }
  trap cleanup EXIT
  if [[ "$package" == *.zip ]]; then
    if ! unzip -q "$package" -d "$work" >>"$LOGS/$name.log" 2>&1; then
      log "extract failed (package corrupt): $name"
      mv -- "$package" "$REJECTED/$name"
      mv -- "$marker_path" "$REJECTED/$(basename "$marker_path")" 2>/dev/null || true
      rm -f -- "$attempts_file"
      exit 30
    fi
  else
    if ! tar -xzf "$package" -C "$work" >>"$LOGS/$name.log" 2>&1; then
      log "extract failed (package corrupt): $name"
      mv -- "$package" "$REJECTED/$name"
      mv -- "$marker_path" "$REJECTED/$(basename "$marker_path")" 2>/dev/null || true
      rm -f -- "$attempts_file"
      exit 30
    fi
  fi
fi

search_root="$work"
if [[ "$is_dir" -eq 1 ]]; then search_root="$package"; fi
mapfile -t manifests < <(find "$search_root" -maxdepth 3 -type f -name manifest.json -print)
if [[ "${#manifests[@]}" -ne 1 ]]; then
  log "package must contain exactly one manifest.json: $name"
  mv -- "$package" "$REJECTED/$name"
  if [[ -n "$marker_path" ]]; then mv -- "$marker_path" "$REJECTED/$(basename "$marker_path")" 2>/dev/null || true; fi
  rm -f -- "$attempts_file"
  exit 30
fi
package_root="$(dirname "${manifests[0]}")"

import_rc=0
if [[ "$predict_mode" -eq 0 ]]; then
  "$PYTHON_BIN" "$NCS_REPO/scripts/import_ads_v23.py" --package "$package_root" --database-url "$NCS_DATABASE_URL" --skip-initialize >>"$LOGS/$name.log" 2>&1 || import_rc=$?
fi

if [[ "$import_rc" -ne 0 ]]; then
  if [[ "$import_rc" -eq 30 ]]; then
    log "import failed with data problem (exit=30): $name"
    mv -- "$package" "$REJECTED/$name"
    if [[ -n "$marker_path" ]]; then mv -- "$marker_path" "$REJECTED/$(basename "$marker_path")" 2>/dev/null || true; fi
    rm -f -- "$attempts_file"
    exit 30
  fi
  attempts=$((attempts + 1))
  if [[ "$attempts" -ge "$MAX_ATTEMPTS" ]]; then
    log "import retry limit reached ($attempts/$MAX_ATTEMPTS): $name"
    mv -- "$package" "$REJECTED/$name"
    if [[ -n "$marker_path" ]]; then mv -- "$marker_path" "$REJECTED/$(basename "$marker_path")" 2>/dev/null || true; fi
    rm -f -- "$attempts_file"
    exit "$import_rc"
  fi
  printf '%s\n' "$attempts" > "$attempts_file"
  log "import failed (exit=$import_rc); will retry ($attempts/$MAX_ATTEMPTS): $name"
  exit "$import_rc"
fi

archive_batch() {
  mv -- "$package" "$ARCHIVE/$name"
  if [[ -n "$marker_path" ]]; then
    mv -- "$marker_path" "$ARCHIVE/$(basename "$marker_path")" 2>/dev/null || true
  fi
  rm -f -- "$attempts_file"
}

if [[ -n "$MODEL_PACKAGE" ]]; then
  prediction_rc=0
  "$PYTHON_BIN" "$NCS_REPO/scripts/run_load_prediction.py" --model-package "$MODEL_PACKAGE" --database-url "$NCS_DATABASE_URL" --horizon "${NCS_PREDICTION_HORIZON:-24}" >>"$LOGS/$name.log" 2>&1 || prediction_rc=$?
  if [[ "$prediction_rc" -ne 0 ]]; then
    attempts=$((attempts + 1))
    if [[ "$attempts" -ge "$MAX_ATTEMPTS" ]]; then
      log "prediction retry limit reached ($attempts/$MAX_ATTEMPTS); ADS stays published, archiving with predictionFailed: $name"
      archive_batch
      log "completed $name (predictionFailed)"
      exit 50
    fi
    printf '%s\n' "$attempts" > "$attempts_file"
    if [[ -n "$marker_path" && "$predict_mode" -eq 0 ]]; then
      mv -- "$marker_path" "$package.ready.predict"
      marker_path="$package.ready.predict"
    fi
    log "prediction failed (exit=$prediction_rc); ADS stays published, prediction-only retry ($attempts/$MAX_ATTEMPTS): $name"
    exit 50
  fi
fi

if [[ "$predict_mode" -eq 1 ]]; then
  log "prediction recovered after retry: $name"
  if [[ -n "$marker_path" ]]; then
    mv -- "$marker_path" "$package.ready" 2>/dev/null || true
    marker_path="$package.ready"
  fi
fi

archive_batch
log "completed $name"
exit 0

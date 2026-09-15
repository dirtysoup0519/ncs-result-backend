#!/usr/bin/env bash
set -Eeuo pipefail

# One-shot starter for the VM ADS sync watcher (README section 3.11).
#
# Usage:
#   start_ads_sync.sh                 foreground watch (default)
#   start_ads_sync.sh --once          run a single sync round and print its exit code
#   start_ads_sync.sh --detach        start watch in the background (nohup + pidfile)
#   start_ads_sync.sh --stop          stop a watcher started with --detach
#   start_ads_sync.sh --env FILE      env file to source
#                                     (default: $NCS_ADS_SYNC_ENV, then
#                                      <repo>/../ncs-runtime/ads-sync.env)
#
# Relative NCS_ADS_EXCHANGE_ROOT values in the env file are resolved against
# the repository directory, matching the README examples.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

usage() { sed -n '2,17p' "${BASH_SOURCE[0]}"; }
ONCE=0
DETACH=0
STOP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env) ENV_FILE="$2"; shift 2 ;;
    --once) ONCE=1; shift ;;
    --detach) DETACH=1; shift ;;
    --stop) STOP=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "start_ads_sync: unknown option: $1" >&2; exit 2 ;;
  esac
done

ENV_FILE="${ENV_FILE:-${NCS_ADS_SYNC_ENV:-$REPO_DIR/../ncs-runtime/ads-sync.env}}"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "start_ads_sync: env file not found: $ENV_FILE" >&2
  echo "create it from scripts/shell/ncs_ads_sync.env.example (see README 3.11)" >&2
  exit 2
fi
# shellcheck disable=SC1090
source "$ENV_FILE"
: "${NCS_REPO:?set NCS_REPO in $ENV_FILE}"
: "${NCS_DATABASE_URL:?set NCS_DATABASE_URL in $ENV_FILE}"

# Normalize paths relative to the repository directory.
if [[ ! -d "$NCS_REPO" && -d "$REPO_DIR" ]]; then
  NCS_REPO="$REPO_DIR"
fi
ROOT="${NCS_ADS_EXCHANGE_ROOT:-/data/ncs/ads_exchange}"
case "$ROOT" in
  /*) ;;
  *) ROOT="$REPO_DIR/$ROOT" ;;
esac
export NCS_REPO NCS_DATABASE_URL NCS_ADS_EXCHANGE_ROOT="$ROOT"
READY="$ROOT/ready"; ARCHIVE="$ROOT/archive"; REJECTED="$ROOT/rejected"
LOGS="$ROOT/logs"; LOCKS="$ROOT/locks"
mkdir -p "$READY" "$ARCHIVE" "$REJECTED" "$LOGS" "$LOCKS"

PID_FILE="$LOCKS/watch_ads.pid"

watch_running() {
  [[ -f "$PID_FILE" ]] || return 1
  local pid
  pid="$(cat "$PID_FILE")"
  kill -0 "$pid" 2>/dev/null
}

if [[ "$STOP" -eq 1 ]]; then
  if ! watch_running; then
    echo "start_ads_sync: watcher is not running (pid file: $PID_FILE)" >&2
    rm -f -- "$PID_FILE"
    exit 1
  fi
  PID="$(cat "$PID_FILE")"
  kill "$PID"
  for _ in $(seq 1 20); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 0.5
  done
  kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null || true
  rm -f -- "$PID_FILE"
  echo "start_ads_sync: watcher $PID stopped"
  exit 0
fi

if [[ "$ONCE" -eq 1 ]]; then
  rc=0
  bash "$REPO_DIR/scripts/shell/sync_ads_once.sh" || rc=$?
  echo "sync_ads_once exit=$rc"
  exit "$rc"
fi

if [[ "$DETACH" -eq 1 ]]; then
  if watch_running; then
    echo "start_ads_sync: watcher already running (pid $(cat "$PID_FILE"))" >&2
    exit 1
  fi
  WATCH_LOG="$LOGS/watch_ads.log"
  nohup bash "$REPO_DIR/scripts/shell/watch_ads.sh" >>"$WATCH_LOG" 2>&1 &
  echo $! > "$PID_FILE"
  echo "start_ads_sync: watcher started in background (pid $!, log: $WATCH_LOG)"
  exit 0
fi

cd "$REPO_DIR"
exec bash "$REPO_DIR/scripts/shell/watch_ads.sh"

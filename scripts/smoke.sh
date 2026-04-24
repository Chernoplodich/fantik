#!/usr/bin/env bash
# Post-deploy smoke: дёргает /healthz + /readyz бота и /metrics всех процессов.
# Возвращает 0 на успех, 1 на любой падающий чек. Используется:
#   - локально: после `make up` (`make smoke`),
#   - в CI: отдельная job,
#   - на staging: как шаг post-deploy.
set -euo pipefail

BOT_URL="${BOT_URL:-http://localhost:8080}"
# Бот отдаёт /metrics на том же aiohttp, что и /healthz — порт 8080.
# Воркеры — на отдельных портах через prometheus_client.start_http_server.
METRICS_BOT_PORT="${METRICS_BOT_PORT:-8080}"
METRICS_WORKER_PORT="${METRICS_WORKER_PORT:-8082}"
METRICS_BROADCAST_PORT="${METRICS_BROADCAST_PORT:-8083}"
METRICS_SCHEDULER_PORT="${METRICS_SCHEDULER_PORT:-8084}"
METRICS_HOST="${METRICS_HOST:-localhost}"
TIMEOUT="${TIMEOUT:-5}"

fail=0

log()  { printf '[smoke] %s\n' "$*"; }
warn() { printf '[smoke] WARN: %s\n' "$*" >&2; fail=1; }

# ---------- healthz / readyz ----------
if curl -fsS --max-time "$TIMEOUT" "$BOT_URL/healthz" >/dev/null; then
  log "healthz ok"
else
  warn "healthz failed ($BOT_URL/healthz)"
fi

if readyz_body=$(curl -fsS --max-time "$TIMEOUT" "$BOT_URL/readyz"); then
  log "readyz: $readyz_body"
  if command -v jq >/dev/null 2>&1; then
    if ! echo "$readyz_body" | jq -e '.pg and .redis' >/dev/null; then
      warn "readyz: pg/redis not healthy"
    fi
  fi
else
  warn "readyz failed ($BOT_URL/readyz)"
fi

# ---------- /metrics: bot + 3 воркерских процесса ----------
check_metrics() {
  local label="$1"; local port="$2"; local must_grep="$3"
  local url="http://${METRICS_HOST}:${port}/metrics"
  if body=$(curl -fsS --max-time "$TIMEOUT" "$url"); then
    if echo "$body" | grep -qE "$must_grep"; then
      log "${label} metrics ok (${port})"
    else
      warn "${label}: /metrics доступен, но нужной метрики нет (${must_grep})"
    fi
  else
    warn "${label}: /metrics недоступен (${url})"
  fi
}

# `bot_tg_api_calls_total` инкрементируется уже на getMe при старте, поэтому
# это надёжнее, чем `bot_updates_total` (ждёт реального апдейта от TG).
check_metrics "bot"          "$METRICS_BOT_PORT"        '^bot_tg_api_calls_total'
check_metrics "worker"       "$METRICS_WORKER_PORT"     '^(worker_task_duration_seconds|moderation_queue_depth|python_info)'
check_metrics "broadcast"    "$METRICS_BROADCAST_PORT"  '^(broadcast_deliveries_total|worker_task_duration_seconds|python_info)'
check_metrics "scheduler"    "$METRICS_SCHEDULER_PORT"  '^(python_info|process_cpu_seconds_total)'

if [[ "$fail" -ne 0 ]]; then
  echo "[smoke] FAILED" >&2
  exit 1
fi
echo "[smoke] OK"

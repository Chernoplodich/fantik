#!/usr/bin/env bash
# Post-deploy smoke: дёргает /healthz + /readyz бота и /metrics всех процессов.
# Возвращает 0 на успех, 1 на любой падающий чек.
#
# Режимы:
#   1. По умолчанию — лезет ВНУТРЬ docker compose стека через `docker compose
#      exec` (читает /healthz из самого bot-контейнера). Работает в prod-режиме,
#      где порты не публикуются на хост.
#   2. SMOKE_MODE=host — старое поведение: curl-ом с хоста на localhost. Нужно
#      когда стек запущен с docker-compose.dev.yml (порты на 127.0.0.1).
#   3. SMOKE_MODE=url — берёт BOT_URL и METRICS_HOST из env (для удалённого
#      smoke после деплоя).
#
# Используется:
#   - локально: `make smoke` после `make up` (auto: docker exec);
#   - в CI: SMOKE_MODE=host после `docker compose -f ... -f dev up`;
#   - после деплоя на staging/prod: SMOKE_MODE=url BOT_URL=https://bot.example.com.

set -euo pipefail

SMOKE_MODE="${SMOKE_MODE:-auto}"
TIMEOUT="${TIMEOUT:-5}"

# Дефолты для host/url режимов.
BOT_URL="${BOT_URL:-http://localhost:8080}"
METRICS_HOST="${METRICS_HOST:-localhost}"
METRICS_BOT_PORT="${METRICS_BOT_PORT:-8080}"
METRICS_WORKER_PORT="${METRICS_WORKER_PORT:-8082}"
METRICS_BROADCAST_PORT="${METRICS_BROADCAST_PORT:-8083}"
METRICS_SCHEDULER_PORT="${METRICS_SCHEDULER_PORT:-8084}"

# Compose-проект (для exec-режима). Можно переопределить переменной окружения,
# если вызываешь скрипт из директории отличной от корня проекта.
COMPOSE_PROJECT="${COMPOSE_PROJECT:-fantik}"

# В auto-режиме: если есть docker compose и есть запущенный bot-контейнер →
# идём в exec, иначе fallback на host-curl.
if [[ "$SMOKE_MODE" == "auto" ]]; then
  if docker compose ps --services --filter status=running 2>/dev/null | grep -q '^bot$'; then
    SMOKE_MODE="exec"
  else
    SMOKE_MODE="host"
  fi
fi

fail=0
log()  { printf '[smoke] %s\n' "$*"; }
warn() { printf '[smoke] WARN: %s\n' "$*" >&2; fail=1; }

# ---------- backend для curl: либо `docker compose exec`, либо локальный curl ----------
# fetch <service> <url-внутри-контейнера>
fetch() {
  local service="$1"; local url="$2"
  if [[ "$SMOKE_MODE" == "exec" ]]; then
    # curl запускается ВНУТРИ контейнера → не нужны host-binding порты.
    docker compose exec -T "$service" curl -fsS --max-time "$TIMEOUT" "$url"
  else
    curl -fsS --max-time "$TIMEOUT" "$url"
  fi
}

log "mode: $SMOKE_MODE"

# ---------- healthz / readyz (bot, порт 8080 в любом режиме внутри контейнера) ----------
if [[ "$SMOKE_MODE" == "exec" ]]; then
  HEALTHZ_URL="http://127.0.0.1:8080/healthz"
  READYZ_URL="http://127.0.0.1:8080/readyz"
else
  HEALTHZ_URL="$BOT_URL/healthz"
  READYZ_URL="$BOT_URL/readyz"
fi

if fetch bot "$HEALTHZ_URL" >/dev/null 2>&1; then
  log "healthz ok"
else
  warn "healthz failed ($HEALTHZ_URL)"
fi

if readyz_body=$(fetch bot "$READYZ_URL" 2>/dev/null); then
  log "readyz: $readyz_body"
  if command -v jq >/dev/null 2>&1; then
    if ! echo "$readyz_body" | jq -e '.pg and .redis' >/dev/null; then
      warn "readyz: pg/redis not healthy"
    fi
  fi
else
  warn "readyz failed ($READYZ_URL)"
fi

# ---------- /metrics: bot + 3 воркерских процесса ----------
# В exec-режиме порты внутри контейнеров: bot/worker/broadcast/scheduler =
# 8080/8082/8083/8084 (worker'ы открывают prometheus_client порт через
# FANTIK_WORKER_METRICS_PORT). В host-режиме — на localhost через dev-overlay.
check_metrics() {
  local label="$1"; local service="$2"; local port="$3"; local must_grep="$4"
  local url
  if [[ "$SMOKE_MODE" == "exec" ]]; then
    url="http://127.0.0.1:${port}/metrics"
  else
    url="http://${METRICS_HOST}:${port}/metrics"
  fi
  if body=$(fetch "$service" "$url" 2>/dev/null); then
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
check_metrics "bot"        "bot"              "${METRICS_BOT_PORT}"       '^bot_tg_api_calls_total'
check_metrics "worker"     "worker"           "${METRICS_WORKER_PORT}"    '^(worker_task_duration_seconds|moderation_queue_depth|python_info)'
check_metrics "broadcast"  "worker-broadcast" "${METRICS_BROADCAST_PORT}" '^(broadcast_deliveries_total|worker_task_duration_seconds|python_info)'
check_metrics "scheduler"  "scheduler"        "${METRICS_SCHEDULER_PORT}" '^(python_info|process_cpu_seconds_total)'

if [[ "$fail" -ne 0 ]]; then
  echo "[smoke] FAILED" >&2
  exit 1
fi
echo "[smoke] OK"

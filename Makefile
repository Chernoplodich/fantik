SHELL := /bin/bash
ENV ?= dev
COMPOSE := docker compose -f docker-compose.yml -f docker-compose.$(ENV).yml

.DEFAULT_GOAL := help

.PHONY: help
help: ## Показать список команд
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

## ---------- Docker ----------

.PHONY: build
build: ## Собрать образ fantik/app:local (один раз — для всех сервисов)
	$(COMPOSE) build bot

.PHONY: rebuild
rebuild: ## Пересобрать образ без кэша
	$(COMPOSE) build --no-cache bot

.PHONY: up
up: ## Поднять стек в фоне
	$(COMPOSE) up -d

.PHONY: up-fg
up-fg: ## Поднять стек в foreground (логи в терминал)
	$(COMPOSE) up

.PHONY: down
down: ## Остановить стек
	$(COMPOSE) down

.PHONY: clean
clean: ## Остановить и удалить volumes (УНИЧТОЖИТ ДАННЫЕ)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Логи (-f), всех сервисов
	$(COMPOSE) logs -f --tail=200

.PHONY: logs-bot
logs-bot: ## Логи bot-сервиса
	$(COMPOSE) logs -f --tail=200 bot

.PHONY: logs-worker
logs-worker: ## Логи worker-сервиса
	$(COMPOSE) logs -f --tail=200 worker

.PHONY: ps
ps: ## Статус контейнеров
	$(COMPOSE) ps

.PHONY: restart-bot
restart-bot: ## Перезапустить bot
	$(COMPOSE) restart bot

## ---------- Dev loop ----------

.PHONY: sync
sync: ## uv sync (установить dev + prod зависимости)
	uv sync

.PHONY: lock
lock: ## Обновить uv.lock
	uv lock

.PHONY: fmt
fmt: ## Форматирование
	uv run ruff format src tests

.PHONY: lint
lint: ## Линт + типы + архитектурные импорты
	uv run ruff check src tests
	uv run ruff format --check src tests
	uv run mypy src
	uv run lint-imports

.PHONY: lint-fix
lint-fix: ## ruff с автопочинкой
	uv run ruff check --fix src tests
	uv run ruff format src tests

## ---------- Tests ----------

.PHONY: test
test: ## Все тесты в контейнере
	$(COMPOSE) run --rm migrate pytest

.PHONY: test-unit
test-unit: ## Unit-тесты локально (без контейнеров)
	uv run pytest tests/unit -v

.PHONY: test-cov
test-cov: ## Тесты с покрытием
	uv run pytest --cov=src --cov-report=term-missing --cov-report=html

## ---------- DB ----------

.PHONY: migrate
migrate: ## alembic upgrade head
	$(COMPOSE) run --rm migrate

.PHONY: migration-new
migration-new: ## Новая автогенерируемая ревизия: make migration-new m="описание"
	$(COMPOSE) run --rm migrate alembic revision --autogenerate -m "$(m)"

.PHONY: migration-empty
migration-empty: ## Пустая ревизия: make migration-empty m="описание"
	$(COMPOSE) run --rm migrate alembic revision -m "$(m)"

.PHONY: downgrade
downgrade: ## Откат на одну ревизию
	$(COMPOSE) run --rm migrate alembic downgrade -1

.PHONY: db-shell
db-shell: ## psql внутри контейнера postgres
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-fantik} $${POSTGRES_DB:-fantik}

.PHONY: redis-cli
redis-cli: ## redis-cli
	$(COMPOSE) exec redis redis-cli

.PHONY: shell
shell: ## Интерактивный Python в bot-контейнере
	$(COMPOSE) exec bot python

## ---------- Setup ----------

.PHONY: init
init: ## Первый запуск: .env из примера, build, migrate, up
	@test -f .env || (cp .env.example .env && echo "→ Создан .env из примера. Открой и заполни BOT_TOKEN, POSTGRES_PASSWORD, MEILI_MASTER_KEY, ADMIN_TG_IDS, потом запусти make init ещё раз.")
	@test -f .env && $(MAKE) build && $(MAKE) migrate && $(MAKE) up && $(MAKE) ps

.PHONY: precommit-install
precommit-install: ## Установить pre-commit хуки
	uv run pre-commit install

.PHONY: precommit-run
precommit-run: ## Прогнать pre-commit по всем файлам
	uv run pre-commit run --all-files

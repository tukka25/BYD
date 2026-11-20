# PromptDash - local stack for testing the fine-tuned chartist.
#
# The model does NOT run in Docker: mlx_lm needs Metal, which a Linux container
# cannot reach. So it runs on the host and the api container reaches it through
# host.docker.internal. Two terminals:
#
#   terminal 1:  make serve-model
#   terminal 2:  make up && make smoke
#
# Run `make help` for everything.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BACKEND      := backend
WEB          := byd-web
FINETUNE     := chartist-finetune
PY           := $(BACKEND)/.venv/bin/python
PIP          := $(BACKEND)/.venv/bin/pip
BASE_MODEL   := models/qwen3.5-9b-4bit
ADAPTER      := runs/adapters-mlx
MLX_PORT     ?= 8080
# 0.0.0.0 so the api CONTAINER can reach it via host.docker.internal. On an
# untrusted network use MLX_HOST=127.0.0.1 and run the backend with `make dev-api`.
MLX_HOST     ?= 0.0.0.0
API_BASE     ?= http://localhost:8000
PROMPT       ?= Monthly MRR trend by plan tier

.PHONY: help setup secrets sample-data adapter serve-model serve-base up down \
        restart logs ps smoke doctor dev-api dev-web test lint

help: ## Show this help
	@echo ""
	@echo "  PromptDash - make targets"
	@echo ""
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "    %-16s %s\n", $$1, $$2}'
	@echo ""
	@echo "  First run:"
	@echo "    make setup         install deps, generate sample CSVs"
	@echo "    make adapter       convert the fine-tuned adapter to MLX format"
	@echo "    make serve-model   (terminal 1) serve the fine-tuned chartist"
	@echo "    make up            (terminal 2) start postgres + api + web"
	@echo "    make smoke         prove it end to end"
	@echo ""

setup: ## Install backend + frontend deps and generate sample data
	@test -d $(BACKEND)/.venv || python3 -m venv $(BACKEND)/.venv
	@$(PIP) install -q -U pip
	@$(PIP) install -q -r $(BACKEND)/requirements.txt
	@$(PIP) install -q langchain-openai
	@cd $(WEB) && npm install --silent
	@$(MAKE) --no-print-directory sample-data
	@echo "setup done. Next: make adapter && make serve-model"

secrets: ## Print fresh SECRET_KEY and ENCRYPTION_KEY for .env
	@echo "# Paste into .env at the repo root. The committed defaults are PUBLIC."
	@$(PY) -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
	@$(PY) -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"

sample-data: ## Generate sample CSVs into backend/uploads
	@$(PY) $(BACKEND)/scripts/make_sample_data.py --out $(BACKEND)/uploads

adapter: ## Convert the PEFT adapter to MLX format (needed once)
	@test -d $(FINETUNE)/cloud/artifacts/out-min || \
	  { echo "No trained adapter at $(FINETUNE)/cloud/artifacts/out-min"; exit 1; }
	@cd $(FINETUNE) && .venv/bin/python cloud/peft_to_mlx.py \
	  --peft cloud/artifacts/out-min --out $(ADAPTER)

serve-model: ## Serve the fine-tuned chartist on the host (blocks)
	@test -d $(FINETUNE)/$(BASE_MODEL) || { echo "Base model missing: $(FINETUNE)/$(BASE_MODEL)"; exit 1; }
	@test -f $(FINETUNE)/$(ADAPTER)/adapters.safetensors || { echo "Run 'make adapter' first"; exit 1; }
	@echo "serving $(BASE_MODEL) + $(ADAPTER) on $(MLX_HOST):$(MLX_PORT)"
	@cd $(FINETUNE) && .venv/bin/python -m mlx_lm server \
	  --model $(BASE_MODEL) --adapter-path $(ADAPTER) \
	  --host $(MLX_HOST) --port $(MLX_PORT)

serve-base: ## Serve the BASE model with no adapter, for comparison
	@cd $(FINETUNE) && .venv/bin/python -m mlx_lm server \
	  --model $(BASE_MODEL) --host $(MLX_HOST) --port $(MLX_PORT)

up: ## Start postgres + api + web
	@$(MAKE) --no-print-directory sample-data
	@docker compose up -d --build
	@echo "waiting for the api to report healthy..."
	@for i in $$(seq 1 40); do \
	  if curl -fsS $(API_BASE)/health >/dev/null 2>&1; then echo "  api is up"; break; fi; \
	  sleep 2; \
	done
	@echo "  api  $(API_BASE)/docs"
	@echo "  web  http://localhost:3000"

down: ## Stop the stack
	@docker compose down

restart: ## Rebuild and restart
	@docker compose up -d --build --force-recreate

logs: ## Tail all logs
	@docker compose logs -f --tail=80

ps: ## Show container status
	@docker compose ps

smoke: ## End-to-end test: health, auth, and a real chart
	@$(PY) $(BACKEND)/scripts/smoke_test.py --base $(API_BASE) --prompt "$(PROMPT)"

doctor: ## Check the things that are usually wrong
	@echo "docker:        $$(docker info >/dev/null 2>&1 && echo running || echo NOT-RUNNING)"
	@echo "api health:    $$(curl -fsS $(API_BASE)/health >/dev/null 2>&1 && echo ok || echo unreachable)"
	@echo "model server:  $$(curl -fsS http://localhost:$(MLX_PORT)/v1/models >/dev/null 2>&1 && echo ok || echo unreachable)"
	@echo "sample CSVs:   $$(ls $(BACKEND)/uploads/*.csv 2>/dev/null | wc -l | tr -d ' ')"
	@echo "mlx adapter:   $$(test -f $(FINETUNE)/$(ADAPTER)/adapters.safetensors && echo present || echo MISSING)"
	@echo "base model:    $$(test -d $(FINETUNE)/$(BASE_MODEL) && echo present || echo MISSING)"

dev-api: ## Run the backend on the host, no docker
	@cd $(BACKEND) && .venv/bin/uvicorn app.main:app --reload --port 8000

dev-web: ## Run the frontend on the host, no docker
	@cd $(WEB) && npm run dev

test: ## Run backend tests
	@cd $(BACKEND) && .venv/bin/python -m pytest -q tests

lint: ## Lint the frontend
	@cd $(WEB) && npm run lint

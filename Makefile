# =============================================================================
# ClinTrial-Stream — Makefile
# =============================================================================
# Single source of truth for project commands. Every contributor starts here.
# Run `make help` to see the menu.

# Use bash (not /bin/sh) for `set -euo pipefail` and modern syntax
SHELL := /usr/bin/env bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

# Variables (override on command line: `make demo EVENTS=1000`)
PYTHON      ?= python3
VENV_DIR    ?= .venv
VENV_PY     := $(VENV_DIR)/bin/python
VENV_PIP    := $(VENV_DIR)/bin/pip
AWS_REGION  ?= eu-west-2
AWS_PROFILE ?= clintrial
ENVIRONMENT ?= dev

# Colors for help output
BLUE   := \033[36m
YELLOW := \033[33m
RESET  := \033[0m

# -----------------------------------------------------------------------------
# Help target — auto-generated from `## comments` after target names
# -----------------------------------------------------------------------------
.PHONY: help
help:  ## Show this help message
	@printf "$(YELLOW)ClinTrial-Stream$(RESET) — available commands:\n\n"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  $(BLUE)%-20s$(RESET) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf "\n  Variables (override with VAR=value):\n"
	@printf "    AWS_REGION   default: $(AWS_REGION)\n"
	@printf "    AWS_PROFILE  default: $(AWS_PROFILE)\n"
	@printf "    ENVIRONMENT  default: $(ENVIRONMENT)\n"

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------
.PHONY: setup
setup: $(VENV_DIR)/bin/activate  ## Create venv and install all dependencies
	$(VENV_PIP) install --upgrade pip setuptools wheel
	$(VENV_PIP) install -e ".[dev]"
	$(VENV_PY) -m pre_commit install
	@printf "\n$(BLUE)Setup complete.$(RESET) Activate with: source $(VENV_DIR)/bin/activate\n"

$(VENV_DIR)/bin/activate:
	$(PYTHON) -m venv $(VENV_DIR)

.PHONY: clean
clean:  ## Remove venv, caches, and build artifacts
	rm -rf $(VENV_DIR) .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# -----------------------------------------------------------------------------
# Code quality
# -----------------------------------------------------------------------------
.PHONY: fmt
fmt:  ## Format code with ruff
	$(VENV_PY) -m ruff format src tests scripts

.PHONY: lint
lint:  ## Run ruff linter
	$(VENV_PY) -m ruff check src tests scripts

.PHONY: lint-fix
lint-fix:  ## Run ruff with auto-fix
	$(VENV_PY) -m ruff check --fix src tests scripts

.PHONY: typecheck
typecheck:  ## Run mypy type checker (strict)
	$(VENV_PY) -m mypy src tests

.PHONY: check
check: lint typecheck  ## Run all static checks (lint + typecheck)

# -----------------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------------
.PHONY: test
test:  ## Run all tests with coverage
	$(VENV_PY) -m pytest

.PHONY: test-unit
test-unit:  ## Run only unit tests
	$(VENV_PY) -m pytest -m unit

.PHONY: test-integration
test-integration:  ## Run only integration tests
	$(VENV_PY) -m pytest -m integration

.PHONY: test-fast
test-fast:  ## Run tests excluding slow ones
	$(VENV_PY) -m pytest -m "not slow"

# -----------------------------------------------------------------------------
# Pre-commit
# -----------------------------------------------------------------------------
.PHONY: pre-commit
pre-commit:  ## Run all pre-commit hooks against every file
	$(VENV_PY) -m pre_commit run --all-files

# -----------------------------------------------------------------------------
# Terraform (infrastructure)
# -----------------------------------------------------------------------------
TF_DIR := infra/terraform/environments/$(ENVIRONMENT)

.PHONY: tf-init
tf-init:  ## Initialize Terraform for the current environment
	cd $(TF_DIR) && terraform init

.PHONY: tf-plan
tf-plan:  ## Show what Terraform would change
	cd $(TF_DIR) && terraform plan

.PHONY: tf-apply
tf-apply:  ## Apply Terraform changes (with confirmation prompt)
	cd $(TF_DIR) && terraform apply

.PHONY: tf-destroy
tf-destroy:  ## Destroy all infrastructure (DESTRUCTIVE)
	@printf "$(YELLOW)WARNING:$(RESET) this will destroy all $(ENVIRONMENT) AWS resources.\n"
	@printf "Type 'yes' to confirm: " && read CONFIRM && [ "$$CONFIRM" = "yes" ]
	cd $(TF_DIR) && terraform destroy

.PHONY: tf-fmt
tf-fmt:  ## Format Terraform files
	cd infra/terraform && terraform fmt -recursive

.PHONY: tf-validate
tf-validate:  ## Validate Terraform syntax
	cd $(TF_DIR) && terraform validate

# -----------------------------------------------------------------------------
# Demo and operations
# -----------------------------------------------------------------------------
EVENTS ?= 1000
RATE ?= 50

.PHONY: demo
demo:  ## Run end-to-end demo (provision, produce, observe, query)
	@printf "$(BLUE)Demo runner not yet implemented$(RESET) — coming in Phase 5.\n"

.PHONY: producer
producer:  ## Run synthetic event producer (EVENTS=N RATE=eps)
	$(VENV_PY) -m clintrial.producer.cli --total-events $(EVENTS) --rate $(RATE)

.PHONY: api
api:  ## Run Flask API locally
	$(VENV_PY) -m clintrial.api.cli

# -----------------------------------------------------------------------------
# CI helpers
# -----------------------------------------------------------------------------
.PHONY: ci
ci: lint typecheck test  ## Run the same checks CI runs

.PHONY: cost
cost:  ## Show current month AWS costs by service
	@aws ce get-cost-and-usage \
	  --time-period Start=$$(date -d "$$(date +%Y-%m-01)" +%Y-%m-%d),End=$$(date +%Y-%m-%d) \
	  --granularity MONTHLY \
	  --metrics UnblendedCost \
	  --group-by Type=DIMENSION,Key=SERVICE \
	  --output json | jq -r '.ResultsByTime[0].Groups[] | select((.Metrics.UnblendedCost.Amount | tonumber) >= 0.01) | "\(.Metrics.UnblendedCost.Amount)\t\(.Keys[0])"' | sort -rn

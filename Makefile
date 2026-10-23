# rom-cli Makefile
# Works seamlessly on Linux, macOS, and Windows (Git Bash / MSYS2 / WSL)

SHELL := /bin/bash
.SHELLFLAGS := -euo pipefail -c
.DEFAULT_GOAL := help

# Paths
PREFIX   ?= $(HOME)
BINDIR   ?= $(PREFIX)/bin
VENV     ?= $(HOME)/.venvs/rom
CACHE    ?= $(HOME)/.cache/rom-cli

# Python detection (skips broken Windows Store aliases and prefers venv if present)
PYTHON   ?= $(shell for c in "$$HOME/.venvs/rom/Scripts/python" "$$HOME/.venvs/rom/bin/python" python py python3; do if command -v "$$c" >/dev/null 2>&1 && "$$c" -c "import sys" >/dev/null 2>&1; then echo "$$c"; exit 0; fi; done; echo python)

.PHONY: help install install-bat uninstall uninstall-all check test clean clean-cache

help: ## Show this help message
	@echo "rom-cli - Retro ROM Search & Downloader CLI"
	@echo ""
	@echo "Usage:"
	@echo "  make <target>"
	@echo ""
	@echo "Targets:"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install rom-cli and dependencies (recommended for Linux/macOS/Git Bash)
	@bash ./install.sh

install-bat: ## Install using native Windows batch script (CMD / PowerShell)
	@cmd.exe //c install.bat

check: ## Check Python syntax of bin and rom package
	@$(PYTHON) -m compileall -q bin rom
	@echo "Syntax check OK"

test: ## Test the installed rom CLI (runs 'rom -l')
	@if [ -x "$(BINDIR)/rom" ]; then \
		"$(BINDIR)/rom" -l; \
	elif [ -f "$(BINDIR)/rom.cmd" ]; then \
		CMD_PATH="$$(cygpath -m "$(BINDIR)/rom.cmd" 2>/dev/null || echo "$(BINDIR)/rom.cmd")"; \
		cmd.exe //c "$$CMD_PATH" -l; \
	else \
		$(PYTHON) bin/rom -l; \
	fi

uninstall: ## Remove installed binary wrappers from ~/bin
	@rm -f "$(BINDIR)/rom" "$(BINDIR)/rom-remote" "$(BINDIR)/rom.cmd"
	@echo "Uninstalled wrappers from $(BINDIR)"

uninstall-all: uninstall ## Remove binary wrappers, virtual environment, and cache
	@rm -rf "$(VENV)"
	@rm -rf "$(CACHE)"
	@echo "Removed virtualenv ($(VENV)) and cache ($(CACHE))"

clean: ## Clean Python bytecode and temporary files
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Cleaned bytecode and cache files"

clean-cache: ## Clean rom-cli metadata and catalog cache
	@rm -rf "$(CACHE)"
	@echo "Cleaned cache directory: $(CACHE)"

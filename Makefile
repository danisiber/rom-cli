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

# Python detection (cross-platform compatible, prefers venv if present)
ifeq ($(OS),Windows_NT)
  VENV_PY := $(USERPROFILE)/.venvs/rom/Scripts/python.exe
  ifneq ($(wildcard $(VENV_PY)),)
    PYTHON ?= $(VENV_PY)
  else
    PYTHON ?= python
  endif
else
  PYTHON ?= $(shell for c in "$$HOME/.venvs/rom/bin/python" python3 python py; do if command -v "$$c" >/dev/null 2>&1 && "$$c" -c "import sys" >/dev/null 2>&1; then echo "$$c"; exit 0; fi; done; echo python)
endif

.PHONY: help run install install-bat exe uninstall uninstall-all check test clean clean-cache

help: ## Show this help message
	@echo rom-cli - Retro ROM Search ^& Downloader CLI
	@echo.
	@echo Usage:
	@echo   make ^<target^>
	@echo.
	@echo Targets:
	@"$(PYTHON)" -c "import re; [print(f'  \033[36m{m.group(1):<16}\033[0m {m.group(2)}') for line in open('Makefile') for m in [re.match(r'^([a-zA-Z_-]+):\s*##\s*(.*)$$', line)] if m]"

run: ## Run rom interactive TUI (or: make run ARGS="-p switch")
	@"$(PYTHON)" bin/rom $(ARGS)

install: ## Install rom-cli and dependencies (recommended for Linux/macOS/Git Bash)
	@bash ./install.sh

install-bat: ## Install using native Windows batch script (CMD / PowerShell)
	@cmd.exe /c install.bat

exe: ## Build standalone Windows executable (dist/rom.exe) using PyInstaller
ifeq ($(OS),Windows_NT)
	@cmd.exe /c build-exe.bat
else
	@echo "Standalone EXE compilation is only supported on Windows"
endif

check: ## Check Python syntax of bin and rom package
	@$(PYTHON) -m compileall -q bin rom
	@echo "Syntax check OK"

test: ## Test the installed rom CLI (runs 'rom -l')
ifeq ($(OS),Windows_NT)
	@"$(PYTHON)" bin/rom -l
else
	@if [ -x "$(BINDIR)/rom" ]; then \
		"$(BINDIR)/rom" -l; \
	elif [ -f "$(BINDIR)/rom.cmd" ]; then \
		CMD_PATH="$$(cygpath -m "$(BINDIR)/rom.cmd" 2>/dev/null || echo "$(BINDIR)/rom.cmd")"; \
		cmd.exe /c "$$CMD_PATH" -l; \
	else \
		$(PYTHON) bin/rom -l; \
	fi
endif

uninstall: ## Remove installed binary wrappers from ~/bin
	@rm -f "$(BINDIR)/rom" "$(BINDIR)/rom-remote" "$(BINDIR)/rom.cmd"
	@echo "Uninstalled wrappers from $(BINDIR)"

uninstall-all: uninstall ## Remove binary wrappers, virtual environment, and cache
	@rm -rf "$(VENV)"
	@rm -rf "$(CACHE)"
	@echo "Removed virtualenv ($(VENV)) and cache ($(CACHE))"

clean: ## Clean Python bytecode, build artifacts, and temporary files
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@rm -rf build dist
	@echo "Cleaned bytecode and build artifacts"

clean-cache: ## Clean rom-cli metadata and catalog cache
	@rm -rf "$(CACHE)"
	@echo "Cleaned cache directory: $(CACHE)"

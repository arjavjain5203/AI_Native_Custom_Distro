#!/usr/bin/env bash
# ──────────────────────────────────────────────
# AI-Native Developer Operating Environment
# Setup Script
# ──────────────────────────────────────────────
# Installs Python dependencies, pulls required Ollama models,
# and starts the AI daemon.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${SCRIPT_DIR}/.venv"
OLLAMA_URL="${OLLAMA_HOST:-http://127.0.0.1:11434}"

# ── Colors ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}→${NC} $*"; }
ok()    { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
fail()  { echo -e "${RED}✗${NC} $*" >&2; exit 1; }

echo ""
echo "┌──────────────────────────────────────────────────────┐"
echo "│  AI-Native Developer Operating Environment  Setup    │"
echo "└──────────────────────────────────────────────────────┘"
echo ""

# ── Python check ──
info "Checking Python installation..."
if ! command -v python3 &>/dev/null; then
    fail "Python 3 is required. Install it with your package manager."
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Python ${PYTHON_VERSION} found"

# ── Virtual environment ──
if [ ! -d "${VENV_DIR}" ]; then
    info "Creating virtual environment..."
    python3 -m venv "${VENV_DIR}"
    ok "Virtual environment created at ${VENV_DIR}"
else
    ok "Virtual environment already exists"
fi

# ── Install dependencies ──
info "Installing Python dependencies..."
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${SCRIPT_DIR}/requirements.txt"
if [ -f "${SCRIPT_DIR}/requirements-dev.txt" ]; then
    "${VENV_DIR}/bin/pip" install --quiet -r "${SCRIPT_DIR}/requirements-dev.txt"
fi
ok "Dependencies installed"

# ── Environment file ──
if [ ! -f "${SCRIPT_DIR}/.env" ]; then
    info "Creating .env from .env.example..."
    cp "${SCRIPT_DIR}/.env.example" "${SCRIPT_DIR}/.env"
    ok ".env created — edit it to add your GITHUB_TOKEN and other settings"
else
    ok ".env already exists"
fi

# ── Ollama check ──
info "Checking Ollama installation..."
if command -v ollama &>/dev/null; then
    ok "Ollama is installed"

    if curl -sf "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
        ok "Ollama is running at ${OLLAMA_URL}"

        info "Pulling required models (this may take a while on first run)..."
        MODELS=("phi3:mini" "gemma:2b" "qwen2.5-coder:1.5b")
        for model in "${MODELS[@]}"; do
            if ollama list 2>/dev/null | grep -q "${model}"; then
                ok "Model ${model} already available"
            else
                info "Pulling ${model}..."
                ollama pull "${model}" || warn "Failed to pull ${model} — you can pull it manually later"
            fi
        done
    else
        warn "Ollama is installed but not running. Start it with: ollama serve"
    fi
else
    warn "Ollama is not installed. Install it from https://ollama.com"
    warn "The daemon will start but model calls will fail without Ollama."
fi

# ── Run tests ──
info "Running tests..."
if "${VENV_DIR}/bin/pytest" -q --tb=short 2>/dev/null; then
    ok "All tests passed"
else
    warn "Some tests failed — this may be expected if Ollama is not running"
fi

echo ""
echo "┌──────────────────────────────────────────────────────┐"
echo "│  Setup complete!                                      │"
echo "│                                                        │"
echo "│  Start the daemon:                                     │"
echo "│    ${VENV_DIR}/bin/python main.py                      │"
echo "│                                                        │"
echo "│  Use the CLI:                                          │"
echo "│    ./ai-os \"create a new python project\"               │"
echo "└──────────────────────────────────────────────────────┘"
echo ""

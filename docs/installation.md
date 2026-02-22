# Installation

## Purpose

This document explains how to install and run the AI-Native Developer Operating Environment, both as a standalone development tool and as part of the custom Arch Linux distribution.

## Quick Start (Standalone)

The fastest way to get running:

```bash
git clone https://github.com/arjavjain5203/AI_Native_Custom_Distro.git
cd AI_Native_Custom_Distro
chmod +x setup.sh
./setup.sh
```

The setup script:

1. Creates a Python virtual environment
2. Installs all dependencies
3. Creates `.env` from `.env.example`
4. Checks Ollama installation
5. Pulls required models (phi3:mini, gemma:2b, qwen2.5-coder:1.5b)
6. Runs the test suite

## Manual Setup

### Prerequisites

- Python 3.12+
- Git
- Ollama ([install guide](https://ollama.com/download))
- Linux (developed on Arch; works on any distro)

### Steps

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings (GITHUB_TOKEN, etc.)

# Pull Ollama models
ollama serve &
ollama pull phi3:mini
ollama pull gemma:2b
ollama pull qwen2.5-coder:1.5b
```

### Start the Daemon

```bash
python main.py
# or
./ai-daemon
```

### Use the CLI

```bash
./ai-os --health
./ai-os "create a new python project"
./ai-os --history 10
```

## Docker Setup

For container-based deployment:

```bash
docker build -t ai-native-dev-os .
docker run -p 8000:8000 ai-native-dev-os
```

> **Note:** The container needs access to a running Ollama instance. Use `--network host` or set the `OLLAMA_HOST` environment variable.

## Configuration

### Environment Variables (`.env`)

Copy `.env.example` to `.env` and configure:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | (empty) | GitHub personal access token |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API URL |
| `AI_OS_API_HOST` | `127.0.0.1` | Daemon bind address |
| `AI_OS_API_PORT` | `8000` | Daemon port |
| `AI_OS_INTENT_MODEL` | `phi3:mini` | Intent classification model |
| `AI_OS_PLANNING_MODEL` | `gemma:2b` | Planning model |
| `AI_OS_CODING_MODEL` | `qwen2.5-coder:1.5b` | Code generation model |
| `AI_OS_ANALYSIS_MODEL` | `gemma:2b` | Analysis model |
| `AI_OS_MODEL_RUNTIME` | `auto` | Runtime selection (auto/ollama/airllm) |
| `AI_OS_MEMORY_DB` | `ai_core.db` | SQLite database path |

### System Configuration (`config.yaml`)

The `config.yaml` file provides centralized configuration for models, agents, tools, and plugins. See the file for all available options.

### Tool Permissions (`permissions.json`)

The `permissions.json` file defines per-tool execution policies:

- `allow` — execute without confirmation
- `prompt` — require user approval
- `deny` — block execution

## Distribution Base (Arch ISO)

The platform can be installed as a full operating environment through the custom Arch Linux ISO.

### ISO Contents

- Arch base system with `i3` desktop
- Python runtime for the daemon
- Core developer tools
- Daemon service files
- Terminal client and configuration
- Ollama runtime (models downloaded post-install)

### Building the ISO

```bash
scripts/sync_runtime.sh
scripts/pre_iso_check.sh
sudo mkarchiso -v -w archiso-work -o out archlive
```

### Installation Flow

1. Boot the custom ISO
2. Install the Arch-based environment
3. Boot into the installed system
4. Enable and start the AI daemon through `systemd`
5. Run first-boot setup
6. Detect hardware and receive model recommendations
7. Accept defaults or choose custom models
8. Download selected models through Ollama

## Hardware Detection and Model Recommendation

The system inspects:

- RAM
- CPU cores
- Available disk space

Based on system resources, it recommends models for each role. The `LOW_MEMORY_THRESHOLD_GB` setting (default 12 GB) determines whether to suggest smaller models for constrained hardware.

Users can:

- install the recommended set
- override recommendations via config or API
- change model assignments later through `POST /models/roles`

## Running Tests

```bash
.venv/bin/pytest -q
```

# Setup Guide

## Purpose

This document explains the configuration files and setup scripts available in the repository, how they work together, and how to customize them.

## Setup Script (`setup.sh`)

The setup script automates the full local development environment setup:

```bash
chmod +x setup.sh
./setup.sh
```

### What it does

1. **Checks Python** — verifies Python 3 is installed
2. **Creates virtual environment** — sets up `.venv/` if it doesn't exist
3. **Installs dependencies** — runs `pip install` for `requirements.txt` and `requirements-dev.txt`
4. **Creates `.env`** — copies `.env.example` to `.env` if not present
5. **Checks Ollama** — verifies Ollama is installed and running
6. **Pulls models** — downloads `phi3:mini`, `gemma:2b`, and `qwen2.5-coder:1.5b`
7. **Runs tests** — executes the test suite to verify the setup

## Configuration Files

### `.env.example` → `.env`

Environment variables for sensitive settings and runtime overrides. Copy to `.env` before running:

```bash
cp .env.example .env
```

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `GITHUB_TOKEN` | (empty) | GitHub personal access token for repository operations |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama API base URL |
| `AI_OS_API_HOST` | `127.0.0.1` | Daemon bind address |
| `AI_OS_API_PORT` | `8000` | Daemon port |
| `AI_OS_INTENT_MODEL` | `phi3:mini` | Model for task classification |
| `AI_OS_PLANNING_MODEL` | `gemma:2b` | Model for plan generation |
| `AI_OS_CODING_MODEL` | `qwen2.5-coder:1.5b` | Model for code tasks |
| `AI_OS_ANALYSIS_MODEL` | `gemma:2b` | Model for diagnostics |
| `AI_OS_MODEL_RUNTIME` | `auto` | Runtime selection (auto/ollama/airllm) |
| `AI_OS_MEMORY_DB` | `ai_core.db` | SQLite database path |

> **Important:** Never commit `.env` to version control. It is listed in `.gitignore`.

### `config.yaml`

Centralized system configuration for models, agents, tools, and plugins:

```yaml
system:
  name: "AI-Native Developer OS"
  version: "0.1.0"
  log_level: "info"
  data_dir: "~/.ai-os"

daemon:
  host: "127.0.0.1"
  port: 8000

ollama:
  base_url: "http://127.0.0.1:11434"
  timeout_seconds: 120

models:
  runtime: "auto"
  roles:
    intent:   "phi3:mini"
    planning: "gemma:2b"
    coding:   "qwen2.5-coder:1.5b"
    analysis: "gemma:2b"

agents:
  planner:
    max_plan_steps: 20
    require_approval: true
  executor:
    retry_on_failure: true
    max_retries: 2
  coding:
    max_file_size_kb: 500
    retrieval_top_k: 5

tools:
  max_concurrent: 4
  shell_timeout_seconds: 30

plugins:
  github:
    enabled: true
  docker:
    enabled: false
```

### `permissions.json`

Granular tool execution permissions. Each tool has a policy that controls whether it can run freely, requires approval, or is blocked:

| Policy | Behavior |
|--------|----------|
| `allow` | Execute without user confirmation |
| `prompt` | Show the operation and ask for approval |
| `deny` | Block execution entirely |

Example entries:

- `read_file: allow` — reading files is always safe
- `write_file: prompt` — writing files requires confirmation
- `install_package: deny` — system package installation is blocked by default
- `git_push: prompt` — pushing to remote always requires confirmation

Edit `permissions.json` to customize the security posture for your environment.

## Dockerfile

The `Dockerfile` provides container deployment:

```bash
docker build -t ai-native-dev-os .
docker run -p 8000:8000 ai-native-dev-os
```

Features:

- Python 3.12 slim base image
- Git and build tools included
- Health check on `/health` endpoint
- Binds to `0.0.0.0:8000` for container networking
- Requires external Ollama instance

## Requirements Files

### `requirements.txt`

Core runtime dependencies:

- `fastapi` — API framework
- `uvicorn` — ASGI server
- `ollama` — Ollama Python client
- `chromadb` — vector storage
- `sentence-transformers` — embedding generation
- `pydantic` — data validation
- `pyyaml` — YAML configuration
- `httpx` — HTTP client

### `requirements-dev.txt`

Development and testing dependencies:

- `pytest` — test framework

## Running the Project

After setup, start the daemon:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Start the daemon
python main.py

# Or use the launcher script
./ai-daemon
```

Use the CLI:

```bash
./ai-os --health
./ai-os "create a new python project"
./ai-os --history 10
```

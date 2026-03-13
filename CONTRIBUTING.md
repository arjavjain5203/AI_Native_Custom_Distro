# Contributing to AI-Native Developer Operating Environment

Thank you for your interest in contributing! This guide will help you get started.

---

## Getting Started

### 1. Fork and Clone

```bash
# Fork the repository on GitHub, then:
git clone https://github.com/arjavjain5203/AI_Native_Custom_Distro.git
cd AI_Native_Custom_Distro
```

### 2. Set Up the Development Environment

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your local settings
```

### 3. Install Ollama

The project requires a local Ollama instance for model inference:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull phi3:mini
ollama pull gemma:2b
```

---

## Running Locally

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

### Run Tests

```bash
pytest -q
```

---

## Making Changes

### Branch Naming

Use descriptive branch names:

```
feature/add-docker-plugin
fix/planner-json-parsing
docs/update-architecture
```

### Code Style

- Python: 4-space indentation, `snake_case` for functions and modules
- Keep imports organized (stdlib → third-party → local)
- Add docstrings to all public functions and classes
- Type-hint function signatures

### Commit Messages

Use short imperative subjects:

```
Add Docker plugin integration
Fix planner JSON extraction for nested plans
Update architecture docs with memory layer
```

---

## Submitting a Pull Request

1. Create a feature branch from `main`
2. Make your changes and commit them
3. Run the full test suite: `pytest -q`
4. Push your branch and open a Pull Request
5. In the PR description, include:
   - Summary of what changed
   - Affected paths (e.g., `ai_core/agents/`, `plugins/`)
   - Validation steps you ran

---

## Architecture Overview

Before contributing, review the documentation:

- [Architecture](docs/architecture.md) — system design and data flow
- [Roadmap](docs/roadmap.md) — development phases and priorities

The core implementation lives in `ai_core/`. Top-level directories
(`agents/`, `daemon/`, `models/`, `memory/`, `tools/`, `plugins/`,
`interfaces/`) provide a clean public interface.

---

## Reporting Issues

When filing an issue, please include:

- Python version (`python3 --version`)
- Ollama version (`ollama --version`)
- Steps to reproduce the problem
- Expected vs. actual behavior
- Relevant log output

---

## Code of Conduct

Be respectful, constructive, and inclusive. We are building developer
tools — let's make the experience great for everyone.

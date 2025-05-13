# AI_Native_Custom_Distro

AI-Native Developer Operating Environment is an Arch-based developer platform with a local AI daemon, terminal interface, tool engine, and Ollama-backed planning.

## Current v1 Core

The repository now contains:

- `archlive/` Arch ISO base
- `docs/` architecture and implementation docs
- `ai_core/` runnable Python AI core
- `ai-os` CLI launcher
- `ai-daemon` FastAPI daemon launcher

## Local Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
```

## Run the Daemon

```bash
.venv/bin/python -m ai_core.daemon.main
```

Or:

```bash
./ai-daemon
```

## Use the CLI

```bash
./ai-os --health
./ai-os create a folder test
./ai-os --history 10
```

## Run Tests

```bash
.venv/bin/pytest -q
```

## Build the ISO

```bash
scripts/sync_runtime.sh
scripts/pre_iso_check.sh
sudo mkarchiso -v -w /home/arjavjain5203/archiso-work -o /home/arjavjain5203/Coding/AI_Native_Custom_Distro archlive
```

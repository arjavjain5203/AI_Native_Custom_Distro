<p align="center">
  <h1 align="center">🧠 AI-Native Developer Operating Environment</h1>
  <p align="center">
    <strong>A Python-based system that integrates local LLMs with Linux to automate developer workflows using natural language.</strong>
  </p>
  <p align="center">
    <a href="#-features">Features</a> •
    <a href="#-architecture">Architecture</a> •
    <a href="#-installation">Installation</a> •
    <a href="#-usage">Usage</a> •
    <a href="#-project-structure">Structure</a> •
    <a href="#-contributing">Contributing</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python">
    <img src="https://img.shields.io/badge/ollama-local%20LLMs-green?logo=ollama" alt="Ollama">
    <img src="https://img.shields.io/badge/fastapi-0.115+-teal?logo=fastapi" alt="FastAPI">
    <img src="https://img.shields.io/badge/license-MIT-purple" alt="License">
    <img src="https://img.shields.io/badge/arch-linux-1793D1?logo=archlinux&logoColor=white" alt="Arch Linux">
  </p>
</p>

---

## 🚀 What Is This?

**AI-Native Developer OS** is an Arch Linux-based developer platform with an always-on local AI daemon. It turns your terminal into an intelligent development environment where you can give commands in plain English — and the system plans, executes, and learns from your workflows.

No cloud APIs. No data leaves your machine. Everything runs locally through [Ollama](https://ollama.com).

---

## 🎥 Demo

> **Coming soon** — screencast showing end-to-end project creation, code modification, and GitHub push using natural language.

<!-- ![demo](docs/assets/demo.gif) -->

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI Terminal** | Natural-language command interface for developer tasks |
| 🧠 **Multi-Agent System** | Planner → Executor → Coding → Analysis pipeline |
| 🔧 **Tool Engine** | Safe execution layer for filesystem, git, shell, and system operations |
| 📦 **Plugin System** | Extensible integrations (GitHub, Docker, and more) |
| 🏠 **100% Local** | All models run on your machine via Ollama — no cloud dependency |
| 💾 **Persistent Memory** | SQLite task history + FAISS semantic code retrieval |
| 🔒 **Permission System** | Granular approval controls for destructive operations |
| ↩️ **Rollback Support** | Undo file changes from any completed task |
| ⚡ **Hardware-Aware** | Automatically selects models based on your system resources |

---

## 🏗️ Architecture

```
User
  │
  ▼
AI Developer Terminal (CLI)
  │
  ▼
Local FastAPI Daemon (port 8000)
  │
  ├──▸ Agent System
  │     ├─ Planner Agent    → decomposes tasks into steps
  │     ├─ Executor Agent   → maps steps to tool calls
  │     ├─ Coding Agent     → code generation with retrieval
  │     └─ Analysis Agent   → diagnostics and error explanation
  │
  ├──▸ Tool Engine
  │     ├─ Filesystem tools
  │     ├─ Git tools
  │     ├─ Shell execution
  │     └─ Plugin tools (GitHub, Docker)
  │
  ├──▸ Model Manager
  │     ├─ Ollama client
  │     ├─ Model router (intent → model selection)
  │     └─ Hardware-aware runtime switching
  │
  └──▸ Memory Layer
        ├─ SQLite (task history, preferences)
        └─ FAISS (semantic code retrieval)
  │
  ▼
Linux OS + Ollama Runtime
```

See [docs/architecture.md](docs/architecture.md) for the full system design.

---

## 📦 Installation

### Prerequisites

- **Python 3.12+**
- **Ollama** — [install guide](https://ollama.com/download)
- **Git**
- **Linux** (developed on Arch; works on any distro)

### Quick Start

```bash
# Clone the repository
git clone https://github.com/arjavjain5203/AI_Native_Custom_Distro.git
cd AI_Native_Custom_Distro

# Run the setup script (creates venv, installs deps, pulls models)
chmod +x setup.sh
./setup.sh
```

### Manual Setup

```bash
# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Pull Ollama models
ollama pull phi3:mini
ollama pull gemma:2b
ollama pull qwen2.5-coder:1.5b
```

### Docker (Optional)

```bash
docker build -t ai-native-dev-os .
docker run -p 8000:8000 ai-native-dev-os
```

> **Note:** The container needs access to a running Ollama instance. Use `--network host` or configure `OLLAMA_HOST` to point to your host's Ollama.

---

## 🎯 Usage

### Start the Daemon

```bash
python main.py
# or
./ai-daemon
```

### Natural Language Commands

```bash
# Check system health
./ai-os --health

# Create a project
./ai-os "create a fastapi project with a health endpoint"

# Work with Git
./ai-os "initialize git, create a .gitignore, and make the first commit"

# Push to GitHub
./ai-os "create a github repo and push the project"

# Analyze code
./ai-os "explain what the main.py file does"

# Modify code
./ai-os "add input validation to the user registration endpoint"

# View task history
./ai-os --history 10
```

### API Endpoints

| Method | Endpoint | Description |
|--------|---------|-------------|
| `GET` | `/health` | Daemon health check |
| `POST` | `/task` | Submit a natural-language task |
| `GET` | `/tasks` | List completed tasks |
| `GET` | `/tasks/{id}` | Get task details |
| `GET` | `/runtime` | Model runtime status |
| `POST` | `/runtime` | Switch model runtime |
| `GET` | `/models` | List configured models |
| `GET` | `/rollback` | List rollback candidates |
| `POST` | `/rollback` | Rollback a task step |

---

## 📁 Project Structure

```
AI_Native_Custom_Distro/
├── main.py                  # Entry point — starts the AI daemon
├── config.yaml              # System configuration
├── permissions.json         # Tool execution permissions
├── setup.sh                 # One-command setup script
├── Dockerfile               # Container deployment
│
├── ai_core/                 # Core implementation package
│   ├── agents/              # Planner, Executor, Coding, Analysis agents
│   ├── cli/                 # Terminal client implementation
│   ├── core/                # Config, execution engine, types, rollback
│   ├── daemon/              # FastAPI daemon application
│   ├── mcp/                 # Model Context Protocol client
│   ├── memory/              # SQLite store, FAISS vector store
│   ├── models/              # Ollama client, model manager, router
│   └── tools/               # Filesystem, git, shell, system tools
│
├── daemon/                  # Daemon module (re-exports ai_core.daemon)
├── agents/                  # Agent module (re-exports ai_core.agents)
├── models/                  # Model module (re-exports ai_core.models)
├── memory/                  # Memory module (re-exports ai_core.memory)
├── plugins/                 # Plugin integrations
│   ├── github_plugin.py     # GitHub repository management
│   └── docker_plugin.py     # Docker container lifecycle
├── interfaces/              # User interfaces
│   ├── terminal.py          # Terminal UI
│   └── voice.py             # Voice interface (planned)
│
├── tools/                   # External tool integrations
├── docs/                    # Documentation
│   ├── architecture.md      # System design
│   ├── roadmap.md           # Development phases
│   └── ...                  # Additional docs
├── tests/                   # Test suite
│   ├── test_agents.py
│   ├── test_api.py
│   ├── test_memory.py
│   └── ...
│
├── archlive/                # Arch ISO build profile
├── scripts/                 # Build and deployment scripts
│
├── requirements.txt         # Python dependencies
├── requirements-dev.txt     # Dev/test dependencies
├── .env.example             # Environment template
├── .gitignore               # Git ignore rules
├── LICENSE                  # MIT License
├── CONTRIBUTING.md          # Contribution guidelines
└── AGENTS.md                # Repository guidelines
```

---

## 🗺️ Roadmap

| Phase | Status | Description |
|-------|--------|-------------|
| 1. Arch Baseline | ✅ Done | ISO build, package layout, i3 desktop |
| 2. AI Daemon | ✅ Done | FastAPI daemon, task lifecycle, health API |
| 3. Terminal Client | ✅ Done | CLI command flow, plan approval |
| 4. Tool Registry | ✅ Done | Permission-gated tool execution |
| 5. GitHub Workflow | ✅ Done | Repo creation, PAT auth, push |
| 6. Persistence | ✅ Done | SQLite history, preferences |
| 7. Code Indexing | ✅ Done | FAISS, chunking, semantic retrieval |
| 8. Coding Workflow | ✅ Done | Retrieval-grounded code editing |
| 9. Diagnostics | 🟡 In Progress | Package management, Analysis Agent |
| 10. ISO Integration | 🟡 In Progress | First-boot setup, model recommendation |
| 11. Stretch | 📋 Planned | Docker plugin, dashboard |

See [docs/roadmap.md](docs/roadmap.md) for detailed phase descriptions.

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for:

- How to fork and clone the repository
- Setting up the development environment
- Running tests
- Submitting pull requests

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).

---

## 🙏 Acknowledgments

- [Ollama](https://ollama.com) — local model execution
- [FastAPI](https://fastapi.tiangolo.com) — API framework
- [Arch Linux](https://archlinux.org) — base operating system
- [FAISS](https://github.com/facebookresearch/faiss) — vector similarity search

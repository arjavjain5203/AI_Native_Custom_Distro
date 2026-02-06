"""Shared configuration values."""

from __future__ import annotations

import os
from pathlib import Path


API_HOST = os.environ.get("AI_OS_API_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("AI_OS_API_PORT", "8000"))
API_BASE_URL = f"http://{API_HOST}:{API_PORT}"

OLLAMA_BASE_URL = os.environ.get("AI_OS_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_INTENT_MODEL = os.environ.get("AI_OS_INTENT_MODEL", "phi3:mini")
OLLAMA_PLANNING_MODEL = os.environ.get("AI_OS_PLANNING_MODEL", "gemma:2b")
OLLAMA_ORCHESTRATOR_MODEL = os.environ.get("AI_OS_ORCHESTRATOR_MODEL", OLLAMA_INTENT_MODEL)
OLLAMA_CODING_MODEL = os.environ.get("AI_OS_CODING_MODEL", "qwen2.5-coder:1.5b")
OLLAMA_ANALYSIS_MODEL = os.environ.get("AI_OS_ANALYSIS_MODEL", OLLAMA_PLANNING_MODEL)

SYSTEM_MODELS_CONFIG_PATH = os.environ.get("AI_OS_SYSTEM_MODELS_CONFIG", "/etc/ai-os/models.json")
USER_MODELS_CONFIG_PATH = os.environ.get(
    "AI_OS_MODELS_CONFIG",
    str(Path.home() / ".ai-os" / "models.json"),
)
DEFAULT_MODEL_RUNTIME = os.environ.get("AI_OS_MODEL_RUNTIME", "auto")
LOW_MEMORY_THRESHOLD_GB = float(os.environ.get("AI_OS_LOW_MEMORY_THRESHOLD_GB", "12"))

DEFAULT_MEMORY_DB = os.environ.get("AI_OS_MEMORY_DB", "ai_core.db")

# Model System

## Purpose

This document describes how the platform uses local models, how models are selected for different tasks, and how lifecycle management works during runtime.

## Model Runtimes

The platform supports two model runtimes:

### Ollama (Primary)

Ollama is the primary local model runtime. It provides:

- install models on demand
- run models locally without building a custom inference stack
- switch between multiple model roles
- keep the system local-first and hardware-aware

The Ollama client (`ai_core/models/ollama.py`) is a minimal HTTP wrapper around the Ollama REST API with support for both streaming and non-streaming responses.

### AirLLM (Alternative)

AirLLM (`ai_core/models/airllm_client.py`) is an alternative runtime for memory-constrained hardware. The Model Manager automatically selects the appropriate runtime based on available system resources.

### Runtime Selection

The `AI_OS_MODEL_RUNTIME` setting controls runtime selection:

- `auto` — automatically selects based on hardware (default)
- `ollama` — force Ollama runtime
- `airllm` — force AirLLM runtime

## Model Roles

The platform uses role-based model assignment. Each role maps to a specific model optimized for that task type.

| Role | Default Model | Purpose |
|------|--------------|---------|
| `intent` | `phi3:mini` | Task classification |
| `planning` | `gemma:2b` | Step generation and plan creation |
| `coding` | `qwen2.5-coder:1.5b` | Code generation and modification |
| `analysis` | `gemma:2b` | Diagnostics and error explanation |
| `orchestrator` | `phi3:mini` | Input classification and agent selection |

Roles can be reassigned at runtime through the `POST /models/roles` API endpoint or through configuration.

## Model Routing

The model routing pipeline (`ai_core/models/router.py`) works as follows:

1. The **Orchestrator** classifies user input into a task type and selects an agent
2. The **Model Router** resolves the classification to a concrete `ModelSelection`
3. The **Model Manager** provides the runtime and model name for the selected role

The Orchestrator includes a keyword-based fallback classifier that works even when Ollama is unavailable, ensuring basic functionality without a running model.

## Orchestrator

The Orchestrator (`ai_core/models/orchestrator.py`) is the decision engine for task routing. It:

- classifies input into task types: `planning`, `coding`, `analysis`, `system`
- selects the appropriate agent: `planning`, `coding`, `analysis`
- determines execution mode: `conversation` vs `execution`
- provides a confidence score for its classification
- falls back to keyword matching when model inference fails

## Model Manager

The Model Manager (`ai_core/models/manager.py`) is the central model lifecycle controller:

- **Hardware Detection** — detects RAM and CPU cores to inform model selection
- **Runtime Switching** — switches between Ollama and AirLLM based on resources
- **Role Assignment** — manages which model handles each task type
- **Model Inventory** — tracks installed and configured models
- **Low Memory Handling** — uses `LOW_MEMORY_THRESHOLD_GB` (default 12 GB) to select smaller models on constrained hardware
- **Model Profiles** — hardware-aware recommendations via `model_profiles.py`

## Configuration

Model configuration is managed through:

- **Environment variables** — `AI_OS_INTENT_MODEL`, `AI_OS_PLANNING_MODEL`, `AI_OS_CODING_MODEL`, `AI_OS_ANALYSIS_MODEL`, `AI_OS_ORCHESTRATOR_MODEL`
- **config.yaml** — centralized YAML configuration under the `models:` section
- **API** — runtime model assignment through `POST /models/roles`
- **Model profiles** — hardware-aware defaults in `ai_core/core/model_profiles.py`

## Installation-Time Recommendation Flow

Models are not bundled in the ISO. During setup or first boot:

1. Hardware is detected (RAM, CPU, disk space)
2. Model profiles recommend suitable models for each role
3. The user can accept defaults or override them
4. Models are downloaded through Ollama after confirmation

## Failure Modes

Common model-related failures include:

- Model not installed
- Insufficient system resources
- Ollama not running
- User-selected model unsuitable for the task
- Network unavailable for model download

The daemon surfaces these conditions clearly and provides corrective actions. The Planner Agent includes rule-based fallback planning so basic commands continue to work without a running model.

## Boundaries

The platform does not attempt to:

- train models
- benchmark every available model family
- support fully automatic model replacement without user awareness
- maintain many simultaneously loaded large models

The focus is stable local execution with configurable model roles.

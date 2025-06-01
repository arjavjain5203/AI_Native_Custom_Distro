"""Shared runtime types."""

from dataclasses import dataclass, field
from typing import Literal
from typing import Any


@dataclass(slots=True)
class PlanStep:
    """A single executable step produced by the planner."""

    description: str
    role: Literal["executor", "coding", "analysis"] = "executor"
    tool_name: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    needs_retrieval: bool = False
    requires_approval: bool = False
    approval_category: str | None = None


@dataclass(slots=True)
class TaskResult:
    """Result returned after executing a task."""

    success: bool
    message: str
    steps: list[PlanStep] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionOutcome:
    """Non-HTTP execution outcome returned by the engine."""

    task_id: str
    command: str
    cwd: str
    result: TaskResult


@dataclass(slots=True)
class ExecutionState:
    """Complete execution state required for deterministic pause/resume."""

    task_id: str
    command: str
    cwd: str
    steps: list[PlanStep] = field(default_factory=list)
    step_index: int = 0
    step_results: list[dict[str, Any]] = field(default_factory=list)
    routing: dict[str, Any] = field(default_factory=dict)
    planning_metadata: dict[str, Any] = field(default_factory=dict)
    context: dict[str, Any] = field(default_factory=dict)
    status: str = "running"


@dataclass(slots=True)
class PlanningResult:
    """Validated planning output."""

    steps: list[PlanStep] = field(default_factory=list)
    source: Literal["model", "fallback"] = "fallback"
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionStepResult:
    """Validated executor output for a single tool step."""

    success: bool
    role: Literal["executor"] = "executor"
    tool_name: str = ""
    output: Any = None
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisStepResult:
    """Validated analysis-agent output."""

    success: bool
    role: Literal["analysis"] = "analysis"
    analysis: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ModelSelection:
    """Model routing decision for a task."""

    task_type: Literal["planning", "coding", "analysis", "system"]
    role: Literal["planning", "coding", "analysis", "system"]
    provider: Literal["ollama", "airllm"]
    model_name: str


@dataclass(slots=True)
class ApprovalRequest:
    """Approval payload returned when a task pauses for confirmation."""

    approval_id: str
    token: str
    task_id: str
    step_index: int
    category: str
    prompt: str


@dataclass(slots=True)
class StepRunResult:
    """Normalized result for executing a single plan step."""

    status: Literal["completed", "pending_approval", "failed"]
    step_index: int
    step: PlanStep
    result: Any = None
    step_result_entry: dict[str, Any] = field(default_factory=dict)
    approval_request: ApprovalRequest | None = None
    failure_analysis: dict[str, Any] | None = None

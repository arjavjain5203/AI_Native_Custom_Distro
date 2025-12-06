from pathlib import Path

import pytest

from ai_core.agents.analysis import AnalysisAgent
from ai_core.agents.executor import ExecutorAgent
from ai_core.agents.planner import PlannerAgent
from ai_core.core.types import PlanStep
from ai_core.models.ollama import OllamaError


class FailingOllamaClient:
    def generate(self, prompt: str, model: str | None = None) -> str:
        raise OllamaError("ollama unavailable")


def test_planner_falls_back_when_ollama_is_unavailable() -> None:
    planner = PlannerAgent(ollama_client=FailingOllamaClient())
    steps = planner.plan("create a folder demo")

    assert len(steps) == 1
    assert steps[0].tool_name == "create_folder"
    assert steps[0].args == {"path": "demo"}


def test_executor_creates_folder_in_cwd(tmp_path: Path) -> None:
    planner = PlannerAgent(ollama_client=FailingOllamaClient())
    executor = ExecutorAgent()

    steps = planner.plan("create a folder project")
    result = executor.execute(steps, cwd=str(tmp_path))

    assert result.success is True
    assert (tmp_path / "project").is_dir()


def test_executor_rejects_non_executor_steps(tmp_path: Path) -> None:
    executor = ExecutorAgent()
    step = PlanStep(
        description="Run coding pipeline",
        role="coding",
        tool_name="coding_pipeline",
        args={"instruction": "update auth"},
    )

    with pytest.raises(ValueError, match="only accepts executor steps"):
        executor.execute_step(step, cwd=str(tmp_path))


class FakeModelManager:
    def get_model_for_task(self, task_type: str) -> str:
        assert task_type == "planning"
        return "mistral-air"

    def run_model(self, model_name: str, prompt: str, *, runtime: str | None = None, task_type: str | None = None) -> str:
        assert model_name == "mistral-air"
        assert task_type == "planning"
        return '[{"description":"Create folder demo","tool_name":"create_folder","args":{"path":"demo"}}]'


def test_planner_can_use_model_manager_for_planning() -> None:
    planner = PlannerAgent(model_manager=FakeModelManager())  # type: ignore[arg-type]

    steps = planner.plan("create a folder demo")

    assert len(steps) == 1
    assert steps[0].tool_name == "create_folder"
    assert steps[0].args == {"path": "demo"}


class FakeAnalysisModelManager:
    def get_model_for_task(self, task_type: str) -> str:
        assert task_type == "analysis"
        return "mistral:7b"

    def run_model(self, model_name: str, prompt: str, *, runtime: str | None = None, task_type: str | None = None) -> str:
        assert model_name == "mistral:7b"
        assert task_type == "analysis"
        return "The failure is caused by a missing dependency."


def test_analysis_agent_returns_structured_result() -> None:
    agent = AnalysisAgent(model_manager=FakeAnalysisModelManager())  # type: ignore[arg-type]

    result = agent.execute_step("debug the traceback", {"traceback": "ImportError"})

    assert result.success is True
    assert result.role == "analysis"
    assert "missing dependency" in result.analysis
    assert result.validation["analysis_length"] > 0

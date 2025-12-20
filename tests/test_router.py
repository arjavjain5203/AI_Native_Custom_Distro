from ai_core.models.router import ModelRouter


class FakeModelManager:
    def get_runtime_for_task(self, task_type: str) -> str:
        return "airllm" if task_type == "coding" else "ollama"

    def get_model_for_task(self, task_type: str) -> str:
        return {
            "coding": "deepseek-coder",
            "analysis": "mistral:7b",
            "system": "mistral:7b",
            "planning": "gemma:2b",
        }[task_type]


class FakeOrchestrator:
    def __init__(self, decision: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.decision = decision
        self.error = error
        self.calls: list[dict[str, object]] = []

    def classify_input(
        self,
        user_input: str,
        context: dict[str, object],
        *,
        session_id: str | None = None,
    ) -> dict[str, object]:
        self.calls.append({"user_input": user_input, "context": context, "session_id": session_id})
        if self.error is not None:
            raise self.error
        assert self.decision is not None
        return self.decision

    def fallback_classification(
        self,
        user_input: str,
        context: dict[str, object],
        *,
        session_id: str | None = None,
    ) -> dict[str, object]:
        return {
            "mode": "execution",
            "task_type": "system",
            "agent": "planning",
            "confidence": 0.82,
        }


def test_router_classifies_coding_tasks() -> None:
    router = ModelRouter(
        model_manager=FakeModelManager(),  # type: ignore[arg-type]
        orchestrator=FakeOrchestrator(
            {
                "mode": "execution",
                "task_type": "coding",
                "agent": "coding",
                "confidence": 0.97,
            }
        ),  # type: ignore[arg-type]
    )

    selection = router.route("add authentication to this fastapi project", {"cwd": "/tmp/project"})

    assert selection.task_type == "coding"
    assert selection.role == "coding"
    assert selection.provider == "airllm"
    assert selection.model_name == "deepseek-coder"

    decision = router.classify("add authentication to this fastapi project", {"cwd": "/tmp/project"}, session_id="project")
    assert decision["task_type"] == "coding"


def test_router_classifies_analysis_and_system_tasks() -> None:
    router = ModelRouter(
        model_manager=FakeModelManager(),  # type: ignore[arg-type]
        orchestrator=FakeOrchestrator(
            {
                "mode": "execution",
                "task_type": "analysis",
                "agent": "analysis",
                "confidence": 0.91,
            }
        ),  # type: ignore[arg-type]
    )

    analysis = router.route("debug this error from the logs", {})

    assert analysis.task_type == "analysis"
    assert analysis.role == "analysis"


def test_router_falls_back_to_rule_classifier_when_orchestrator_fails() -> None:
    router = ModelRouter(
        model_manager=FakeModelManager(),  # type: ignore[arg-type]
        orchestrator=FakeOrchestrator(error=RuntimeError("orchestrator unavailable")),  # type: ignore[arg-type]
    )

    system = router.route("install package docker", {})

    assert system.task_type == "system"
    assert system.role == "planning"

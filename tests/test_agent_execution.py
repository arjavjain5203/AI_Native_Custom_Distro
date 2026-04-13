"""Tests for agent execution flow."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestPlannerAgent:
    """Validate PlannerAgent behavior."""

    def test_planner_handles_empty_command(self) -> None:
        """An empty command should raise ValueError."""
        from ai_core.agents.planner import PlannerAgent

        mock_manager = MagicMock()
        planner = PlannerAgent(model_manager=mock_manager)

        with pytest.raises(ValueError, match="cannot be empty"):
            planner.plan("")

    def test_planner_fallback_create_folder(self) -> None:
        """A 'create folder' command should produce a fallback plan."""
        from ai_core.agents.planner import PlannerAgent
        from ai_core.models.manager import ModelManagerError

        mock_manager = MagicMock()
        mock_manager.run_role_model.side_effect = ModelManagerError("no model")
        planner = PlannerAgent(model_manager=mock_manager)

        steps = planner.plan("create folder test_dir")
        assert len(steps) == 1
        assert steps[0].tool_name == "create_folder"
        assert steps[0].args["path"] == "test_dir"

    def test_planner_fallback_git_init(self) -> None:
        """A 'git init' command should produce a fallback plan."""
        from ai_core.agents.planner import PlannerAgent
        from ai_core.models.manager import ModelManagerError

        mock_manager = MagicMock()
        mock_manager.run_role_model.side_effect = ModelManagerError("no model")
        planner = PlannerAgent(model_manager=mock_manager)

        steps = planner.plan("git init")
        assert len(steps) == 1
        assert steps[0].tool_name == "git_init"

    def test_planner_fallback_list_files(self) -> None:
        """A 'list files in current directory' command should produce a fallback plan."""
        from ai_core.agents.planner import PlannerAgent
        from ai_core.models.manager import ModelManagerError

        mock_manager = MagicMock()
        mock_manager.run_role_model.side_effect = ModelManagerError("no model")
        planner = PlannerAgent(model_manager=mock_manager)

        steps = planner.plan("list files in current directory")
        assert len(steps) == 1
        assert steps[0].tool_name == "list_files"

    def test_planner_fallback_read_file(self) -> None:
        """A 'read file' command should produce a fallback plan."""
        from ai_core.agents.planner import PlannerAgent
        from ai_core.models.manager import ModelManagerError

        mock_manager = MagicMock()
        mock_manager.run_role_model.side_effect = ModelManagerError("no model")
        planner = PlannerAgent(model_manager=mock_manager)

        steps = planner.plan("read file main.py")
        assert len(steps) == 1
        assert steps[0].tool_name == "read_file"
        assert steps[0].args["path"] == "main.py"


class TestExecutorAgent:
    """Validate ExecutorAgent behavior."""

    def test_executor_initializes(self) -> None:
        """The executor should initialize without errors."""
        from ai_core.agents.executor import ExecutorAgent

        executor = ExecutorAgent()
        assert executor is not None


class TestCodingAgent:
    """Validate CodingAgent behavior."""

    def test_coding_agent_initializes(self) -> None:
        """The coding agent should initialize with required dependencies."""
        from ai_core.agents.coding import CodingAgent

        mock_manager = MagicMock()
        mock_vector = MagicMock()
        mock_registry = MagicMock()

        agent = CodingAgent(
            model_manager=mock_manager,
            vector_store=mock_vector,
            tool_registry=mock_registry,
        )
        assert agent is not None


class TestAnalysisAgent:
    """Validate AnalysisAgent behavior."""

    def test_analysis_agent_initializes(self) -> None:
        """The analysis agent should initialize properly."""
        from ai_core.agents.analysis import AnalysisAgent

        mock_manager = MagicMock()
        agent = AnalysisAgent(model_manager=mock_manager)
        assert agent is not None

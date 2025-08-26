"""Planner agent with role-aware planning and rule-based fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from ai_core.core.config import OLLAMA_PLANNING_MODEL
from ai_core.core.types import PlanStep, PlanningResult
from ai_core.models.airllm_client import AirLLMError
from ai_core.models.manager import ModelManager, ModelManagerError
from ai_core.models.ollama import OllamaClient, OllamaError


class PlannerAgent:
    """Convert a natural language command into an execution plan."""

    def __init__(
        self,
        ollama_client: OllamaClient | None = None,
        planning_model: str = OLLAMA_PLANNING_MODEL,
        model_manager: ModelManager | None = None,
    ) -> None:
        self.ollama_client = ollama_client or OllamaClient()
        self.planning_model = planning_model
        self.model_manager = model_manager
        self.allowed_tools = {
            "clone_repo",
            "create_branch",
            "create_file",
            "create_folder",
            "create_repository",
            "docker_check",
            "docker_run_command",
            "git_commit",
            "git_init",
            "list_files",
            "pacman_install",
            "pacman_query",
            "pacman_remove",
            "push_changes",
            "read_file",
            "update_file",
            "write_file",
            "coding_pipeline",
            "analysis_pipeline",
        }

    def plan(self, command: str) -> list[PlanStep]:
        """Compatibility wrapper returning only the validated plan steps."""
        return self.plan_task(command).steps

    def plan_task(self, command: str) -> PlanningResult:
        """Create a validated plan without executing any step."""
        cleaned = command.strip()
        if not cleaned:
            raise ValueError("command cannot be empty")

        try:
            llm_plan = self._plan_with_model(cleaned)
            if llm_plan:
                return PlanningResult(
                    steps=llm_plan,
                    source="model",
                    validation=self._build_validation(llm_plan),
                )
        except (AirLLMError, ModelManagerError, OllamaError):
            pass
        except ValueError:
            pass

        fallback_steps = self._fallback_plan(cleaned)
        return PlanningResult(
            steps=fallback_steps,
            source="fallback",
            validation=self._build_validation(fallback_steps),
        )

    def _plan_with_model(self, command: str) -> list[PlanStep]:
        prompt = self._build_prompt(command)
        if self.model_manager is not None:
            model_name = self.model_manager.get_model_for_task("planning")
            response = self.model_manager.run_model(model_name, prompt, task_type="planning")
        else:
            response = self.ollama_client.generate(prompt, model=self.planning_model)
        return self._parse_llm_plan(response)

    def _build_prompt(self, command: str) -> str:
        allowed_tools = ", ".join(sorted(self.allowed_tools))
        return f"""
You are a planning assistant for a local developer operating environment.
Convert the user request into a JSON array of plan steps.

Rules:
- Output valid JSON only.
- Each step must have keys: description, role, tool_name, args.
- Optional keys: needs_retrieval, requires_approval, approval_category.
- Allowed role values: executor, coding, analysis.
- Allowed tool_name values: {allowed_tools}.
- Use approval_category only for risky actions such as git_push, package_install, shell_command, file_overwrite.
- Keep the plan short and executable.
- If the task is unsupported, output [].

User command: {command}
""".strip()

    def _parse_llm_plan(self, response: str) -> list[PlanStep]:
        raw_data: Any = json.loads(response)
        if not isinstance(raw_data, list):
            raise ValueError("planning output must be a JSON array")

        steps: list[PlanStep] = []
        for item in raw_data:
            if not isinstance(item, dict):
                raise ValueError("each plan step must be an object")

            description = item.get("description")
            role = item.get("role", "executor")
            tool_name = item.get("tool_name")
            args = item.get("args", {})
            needs_retrieval = bool(item.get("needs_retrieval", False))
            requires_approval = bool(item.get("requires_approval", False))
            approval_category = item.get("approval_category")

            if not isinstance(description, str) or not description.strip():
                raise ValueError("step description must be a non-empty string")
            if role not in {"executor", "coding", "analysis"}:
                raise ValueError(f"unsupported step role: {role}")
            if tool_name not in self.allowed_tools:
                raise ValueError(f"unsupported tool from planner: {tool_name}")
            if not isinstance(args, dict):
                raise ValueError("step args must be an object")
            if approval_category is not None and not isinstance(approval_category, str):
                raise ValueError("approval_category must be a string when provided")

            steps.append(
                PlanStep(
                    description=description.strip(),
                    role=role,
                    tool_name=tool_name,
                    args=args,
                    needs_retrieval=needs_retrieval,
                    requires_approval=requires_approval,
                    approval_category=approval_category,
                )
            )

        if not steps:
            raise ValueError("planner returned an empty plan")

        return steps

    def _build_validation(self, steps: list[PlanStep]) -> dict[str, Any]:
        step_roles = {step.role for step in steps}
        for step in steps:
            self._validate_step_contract(step)
        return {
            "step_count": len(steps),
            "roles": sorted(step_roles),
            "executor_steps": sum(1 for step in steps if step.role == "executor"),
            "coding_steps": sum(1 for step in steps if step.role == "coding"),
            "analysis_steps": sum(1 for step in steps if step.role == "analysis"),
        }

    def _fallback_plan(self, cleaned: str) -> list[PlanStep]:
        lower = cleaned.lower()

        folder_match = re.match(r"^(?:create|make)\s+(?:a\s+)?folder\s+(.+)$", cleaned, re.IGNORECASE)
        if folder_match:
            path = folder_match.group(1).strip()
            return [self._executor_step(f"Create folder {path}", "create_folder", {"path": path})]

        file_match = re.match(r"^(?:create|make)\s+(?:a\s+)?file\s+(.+)$", cleaned, re.IGNORECASE)
        if file_match:
            path = file_match.group(1).strip()
            return [self._executor_step(f"Create file {path}", "create_file", {"path": path, "content": ""})]

        read_match = re.match(r"^read\s+(?:the\s+)?file\s+(.+)$", cleaned, re.IGNORECASE)
        if read_match:
            path = read_match.group(1).strip()
            return [self._executor_step(f"Read file {path}", "read_file", {"path": path})]

        if lower in {"git init", "initialize git", "init git"}:
            return [self._executor_step("Initialize git repository", "git_init", {})]

        commit_match = re.match(r"^(?:git\s+)?commit(?:\s+with\s+message)?\s+(.+)$", cleaned, re.IGNORECASE)
        if commit_match:
            message = commit_match.group(1).strip().strip("\"'")
            return [self._executor_step(f"Commit repository changes with message: {message}", "git_commit", {"message": message})]

        clone_match = re.match(r"^clone\s+repo\s+(.+)$", cleaned, re.IGNORECASE)
        if clone_match:
            repo_url = clone_match.group(1).strip()
            repo_name = repo_url.rstrip("/").split("/")[-1].removesuffix(".git")
            return [self._executor_step(f"Clone repository {repo_url}", "clone_repo", {"repo_url": repo_url, "destination": repo_name})]

        branch_match = re.match(r"^(?:create\s+)?branch\s+(.+)$", cleaned, re.IGNORECASE)
        if branch_match:
            branch_name = branch_match.group(1).strip()
            return [self._executor_step(f"Create branch {branch_name}", "create_branch", {"branch_name": branch_name})]

        if re.match(r"^(?:git\s+)?push(?:\s+changes)?", cleaned, re.IGNORECASE):
            return [
                self._executor_step(
                    "Push repository changes",
                    "push_changes",
                    {},
                    requires_approval=True,
                    approval_category="git_push",
                )
            ]

        package_match = re.match(r"^install\s+package\s+(.+)$", cleaned, re.IGNORECASE)
        if package_match:
            package_name = package_match.group(1).strip()
            return [
                self._executor_step(
                    f"Install package {package_name}",
                    "pacman_install",
                    {"package": package_name},
                    requires_approval=True,
                    approval_category="package_install",
                )
            ]

        if re.match(r"^check\s+docker$", cleaned, re.IGNORECASE):
            return [self._executor_step("Check Docker availability", "docker_check", {})]

        if self._looks_like_analysis(cleaned):
            return [
                PlanStep(
                    description=f"Analyze issue: {cleaned}",
                    role="analysis",
                    tool_name="analysis_pipeline",
                    args={"instruction": cleaned},
                )
            ]

        if self._looks_like_coding(cleaned):
            return [
                PlanStep(
                    description=f"Apply coding workflow for: {cleaned}",
                    role="coding",
                    tool_name="coding_pipeline",
                    args={"instruction": cleaned},
                    needs_retrieval=True,
                )
            ]

        raise ValueError(f"unsupported command for v1 planner: {cleaned}")

    @staticmethod
    def _executor_step(
        description: str,
        tool_name: str,
        args: dict[str, Any],
        *,
        requires_approval: bool = False,
        approval_category: str | None = None,
    ) -> PlanStep:
        return PlanStep(
            description=description,
            role="executor",
            tool_name=tool_name,
            args=args,
            requires_approval=requires_approval,
            approval_category=approval_category,
        )

    @staticmethod
    def _validate_step_contract(step: PlanStep) -> None:
        if step.role == "coding" and step.tool_name != "coding_pipeline":
            raise ValueError("coding steps must use the coding_pipeline tool")
        if step.role == "analysis" and step.tool_name != "analysis_pipeline":
            raise ValueError("analysis steps must use the analysis_pipeline tool")
        if step.role == "executor" and step.tool_name in {"coding_pipeline", "analysis_pipeline"}:
            raise ValueError("executor steps cannot use pipeline tools")

    @staticmethod
    def _looks_like_coding(command: str) -> bool:
        return bool(
            re.search(
                r"\b(add|modify|edit|refactor|fix|update|implement|write)\b.*\b(code|function|class|endpoint|api|auth|feature|repository|repo|project)\b",
                command,
                re.IGNORECASE,
            )
        )

    @staticmethod
    def _looks_like_analysis(command: str) -> bool:
        return bool(
            re.search(
                r"\b(analyze|debug|diagnose|explain|inspect|investigate)\b|\b(error|failure|issue|log|traceback|status)\b",
                command,
                re.IGNORECASE,
            )
        )

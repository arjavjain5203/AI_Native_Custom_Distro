"""Coding agent for bounded repository edits."""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field
import difflib
import json
from pathlib import Path
import re
from typing import Any

from ai_core.core.file_verifier import resolve_tool_targets, snapshot_paths, verify_path_mutations
from ai_core.memory.vector_store import VectorStore
from ai_core.models.manager import ModelManager
from ai_core.tools import ToolExecutionContext, ToolExecutionError, ToolRegistry, build_tool_registry, list_files, run_shell_command


MAX_RETRIES = 2
TEST_TRIGGER_PATTERN = re.compile(r"\b(run tests|test it|run pytest|verify)\b", re.IGNORECASE)
BUILTIN_NAMES = set(dir(builtins))


@dataclass(slots=True)
class CodingStepResult:
    """Result of a coding step."""

    success: bool
    changed_files: list[str]
    diffs: dict[str, str]
    retrieved_files: list[str]
    validation: dict[str, Any]
    actions: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model_response: str = ""
    error: str | None = None
    tests: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class _EditGenerationResult:
    """Internal result for candidate edit generation and validation."""

    success: bool
    actions: list[dict[str, Any]]
    validation: dict[str, Any]
    retries_used: int
    raw_response: str = ""
    error: str | None = None


class CodingAgent:
    """Perform bounded code generation and modification tasks."""

    def __init__(
        self,
        model_manager: ModelManager | None = None,
        vector_store: VectorStore | None = None,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.model_manager = model_manager or ModelManager()
        self.vector_store = vector_store or VectorStore()
        self.tool_registry = tool_registry or build_tool_registry()

    def execute_step(self, instruction: str, cwd: str, step_args: dict[str, Any]) -> CodingStepResult:
        self._validate_inputs(instruction, cwd, step_args)
        repo_root = Path(cwd).expanduser().resolve()
        indexed = self.vector_store.index_repository(repo_root)
        retrieved = self.vector_store.search(repo_root, instruction, limit=5)
        if not isinstance(retrieved, list):
            raise ValueError("vector store search must return a list")
        model_name = self.model_manager.get_model_for_task("coding")
        prompt = self._build_prompt(instruction, retrieved, indexed)
        generation = self._generate_validated_edits(
            instruction=instruction,
            repo_root=repo_root,
            retrieved=retrieved,
            indexed_count=indexed,
            model_name=model_name,
            initial_prompt=prompt,
        )
        retrieved_files = [item["file_path"] for item in retrieved]
        tests = self._empty_test_results()

        if not generation.success:
            validation = self._finalize_validation(
                repo_root=repo_root,
                changed_files=[],
                validation=generation.validation,
                retries_used=generation.retries_used,
            )
            result = CodingStepResult(
                success=False,
                error=generation.error or "Validation failed after retries",
                changed_files=[],
                diffs={},
                retrieved_files=retrieved_files,
                validation=validation,
                actions=[],
                tool_calls=[],
                model_response=generation.raw_response,
                tests=tests,
            )
            self._validate_result(result)
            return result

        changed_files: list[str] = []
        diffs: dict[str, str] = {}
        tool_calls: list[dict[str, Any]] = []
        try:
            for action in generation.actions:
                tool_name, tool_args = self._action_to_tool(action)
                target_paths = resolve_tool_targets(tool_name, tool_args, str(repo_root))
                snapshots = snapshot_paths(target_paths)
                old_content = ""
                relative_path = self._action_display_path(action)
                if relative_path:
                    target_path = (repo_root / relative_path).resolve()
                    if not str(target_path).startswith(str(repo_root)):
                        raise ValueError(f"refusing to edit outside repository: {target_path}")
                    if target_path.exists() and target_path.is_file():
                        old_content = target_path.read_text(encoding="utf-8", errors="replace")

                tool_result = self.tool_registry.execute(
                    tool_name,
                    tool_args,
                    ToolExecutionContext(
                        cwd=str(repo_root),
                        metadata={"role": "coding", "tool_name": tool_name},
                    ),
                )
                if not tool_result.success:
                    raise ValueError(tool_result.error or f"coding tool execution failed: {tool_name}")
                if tool_result.output is None or (isinstance(tool_result.output, str) and not tool_result.output.strip()):
                    raise ValueError(f"coding tool execution returned no valid output: {tool_name}")

                verification = verify_path_mutations(snapshots, cwd=str(repo_root))
                modified_paths = verification["files_modified"]
                if not modified_paths:
                    raise ValueError(f"coding action '{tool_name}' produced no verified file changes")

                for modified_path in modified_paths:
                    if modified_path not in changed_files:
                        changed_files.append(modified_path)

                if relative_path:
                    target_path = (repo_root / relative_path).resolve()
                    if target_path.exists() and target_path.is_file():
                        new_content = target_path.read_text(encoding="utf-8", errors="replace")
                        diff = "\n".join(
                            difflib.unified_diff(
                                old_content.splitlines(),
                                new_content.splitlines(),
                                fromfile=f"a/{relative_path}",
                                tofile=f"b/{relative_path}",
                                lineterm="",
                            )
                        )
                        if diff:
                            diffs[relative_path] = diff

                tool_calls.append(
                    {
                        "tool_name": tool_name,
                        "args": tool_args,
                        "output": tool_result.output,
                        "verification": verification,
                    }
                )
        except Exception as exc:
            validation = self._finalize_validation(
                repo_root=repo_root,
                changed_files=[],
                validation={
                    **generation.validation,
                    "errors": list(generation.validation.get("errors", [])) + [str(exc)],
                },
                retries_used=generation.retries_used,
            )
            result = CodingStepResult(
                success=False,
                error=str(exc),
                changed_files=[],
                diffs={},
                retrieved_files=retrieved_files,
                validation=validation,
                actions=generation.actions,
                tool_calls=tool_calls,
                model_response=generation.raw_response,
                tests=tests,
            )
            self._validate_result(result)
            return result

        if not changed_files:
            validation = self._finalize_validation(
                repo_root=repo_root,
                changed_files=[],
                validation={
                    **generation.validation,
                    "errors": list(generation.validation.get("errors", [])) + ["no verified file changes detected"],
                },
                retries_used=generation.retries_used,
            )
            result = CodingStepResult(
                success=False,
                error="No verified file changes detected",
                changed_files=[],
                diffs={},
                retrieved_files=retrieved_files,
                validation=validation,
                actions=generation.actions,
                tool_calls=tool_calls,
                model_response=generation.raw_response,
                tests=tests,
            )
            self._validate_result(result)
            return result

        validation = self._finalize_validation(
            repo_root=repo_root,
            changed_files=changed_files,
            validation=generation.validation,
            retries_used=generation.retries_used,
        )
        tests = self._maybe_run_tests(repo_root, instruction, step_args)
        result = CodingStepResult(
            success=True,
            changed_files=changed_files,
            diffs=diffs,
            retrieved_files=retrieved_files,
            validation=validation,
            actions=generation.actions,
            tool_calls=tool_calls,
            model_response=generation.raw_response,
            tests=tests,
        )
        self._validate_result(result)
        return result

    def _build_prompt(self, instruction: str, retrieved: list[dict[str, Any]], indexed_count: int) -> str:
        context = "\n\n".join(
            f"File: {item['file_path']}\n{item['content']}" for item in retrieved
        )
        return f"""
You are a coding agent for a local developer operating environment.
The repository has {indexed_count} indexed chunks.

User instruction:
{instruction}

Relevant context:
{context}

Return JSON only in this format:
{{
  "actions": [
    {{
      "action": "edit_file",
      "file": "relative/path.py",
      "content": "full new file contents"
    }}
  ]
}}

Rules:
- Do not return prose.
- Use only action names: create_file, edit_file, create_folder.
- Every requested code change must be expressed through actions.
- If you do not intend to modify a file or folder, return an empty actions array.
""".strip()

    def _build_correction_prompt(
        self,
        instruction: str,
        retrieved: list[dict[str, Any]],
        indexed_count: int,
        previous_response: str,
        validation_errors: list[str],
    ) -> str:
        base_prompt = self._build_prompt(instruction, retrieved, indexed_count)
        error_block = "\n".join(f"- {error}" for error in validation_errors)
        return f"""
{base_prompt}

The previous candidate edits were invalid.
Validation errors:
{error_block}

Previous response:
{previous_response}

Fix the code and return corrected JSON only in the same format.
Do not explain.
""".strip()

    @staticmethod
    def _parse_edits(response: str) -> list[dict[str, Any]]:
        payload = json.loads(response)
        actions = payload.get("actions", [])
        if not isinstance(actions, list):
            raise ValueError("coding response must contain an actions list")

        normalized: list[dict[str, Any]] = []
        for action in actions:
            if not isinstance(action, dict):
                raise ValueError("each action must be an object")
            action_name = action.get("action")
            if not isinstance(action_name, str) or not action_name.strip():
                raise ValueError("action name must be a non-empty string")
            normalized_action = {"action": action_name.strip()}
            if action_name in {"create_file", "edit_file"}:
                path = action.get("file")
                content = action.get("content")
                if not isinstance(path, str) or not path.strip():
                    raise ValueError(f"{action_name} requires a non-empty 'file' value")
                if not isinstance(content, str):
                    raise ValueError(f"{action_name} requires a string 'content' value")
                normalized_action["file"] = path.strip()
                normalized_action["content"] = content
            elif action_name == "create_folder":
                path = action.get("path")
                if not isinstance(path, str) or not path.strip():
                    raise ValueError("create_folder requires a non-empty 'path' value")
                normalized_action["path"] = path.strip()
            else:
                raise ValueError(f"unsupported coding action: {action_name}")
            normalized.append(normalized_action)
        return normalized

    def _generate_validated_edits(
        self,
        *,
        instruction: str,
        repo_root: Path,
        retrieved: list[dict[str, Any]],
        indexed_count: int,
        model_name: str,
        initial_prompt: str,
    ) -> _EditGenerationResult:
        prompt = initial_prompt
        last_errors: list[str] = []
        last_response = ""
        last_validation = {
            "syntax_ok": False,
            "imports_ok": True,
            "python_files_checked": [],
            "errors": [],
            "warnings": [],
        }

        for attempt in range(MAX_RETRIES + 1):
            last_response = self.model_manager.run_model(model_name, prompt, task_type="coding")
            try:
                actions = self._parse_edits(last_response)
            except (json.JSONDecodeError, ValueError) as exc:
                last_errors = [str(exc)]
                last_validation = {
                    "syntax_ok": False,
                    "imports_ok": True,
                    "python_files_checked": [],
                    "errors": list(last_errors),
                    "warnings": [],
                }
                if attempt == MAX_RETRIES:
                    break
                prompt = self._build_correction_prompt(
                    instruction,
                    retrieved,
                    indexed_count,
                    last_response,
                    last_errors,
                )
                continue

            if not actions:
                last_errors = ["coding response did not include any actionable tool calls"]
                last_validation = {
                    "syntax_ok": False,
                    "imports_ok": True,
                    "python_files_checked": [],
                    "errors": list(last_errors),
                    "warnings": [],
                }
                if attempt == MAX_RETRIES:
                    break
                prompt = self._build_correction_prompt(
                    instruction,
                    retrieved,
                    indexed_count,
                    last_response,
                    last_errors,
                )
                continue

            validation = self._validate_candidate_edits(repo_root, actions)
            last_validation = validation
            if validation["syntax_ok"]:
                return _EditGenerationResult(
                    success=True,
                    actions=actions,
                    validation=validation,
                    retries_used=attempt,
                    raw_response=last_response,
                )

            last_errors = list(validation["errors"])
            if attempt == MAX_RETRIES:
                break
            prompt = self._build_correction_prompt(
                instruction,
                retrieved,
                indexed_count,
                json.dumps({"actions": actions}, indent=2),
                last_errors,
            )

        return _EditGenerationResult(
            success=False,
            actions=[],
            validation=last_validation,
            retries_used=MAX_RETRIES,
            raw_response=last_response,
            error="Validation failed after retries",
        )

    def _validate_candidate_edits(self, repo_root: Path, actions: list[dict[str, Any]]) -> dict[str, Any]:
        syntax_errors: list[str] = []
        warnings: list[str] = []
        python_files_checked: list[str] = []
        file_actions = [action for action in actions if action["action"] in {"create_file", "edit_file"}]
        local_module_roots = self._discover_local_module_roots(repo_root, file_actions)

        for action in file_actions:
            relative_path = str(action["file"])
            if not relative_path.endswith(".py"):
                continue
            python_files_checked.append(relative_path)
            try:
                tree = ast.parse(str(action["content"]), filename=relative_path)
            except SyntaxError as exc:
                syntax_errors.append(self._format_syntax_error(relative_path, exc))
                continue

            warnings.extend(
                self._validate_python_imports(
                    tree=tree,
                    relative_path=relative_path,
                    repo_root=repo_root,
                    edits=file_actions,
                    local_module_roots=local_module_roots,
                )
            )

        return {
            "syntax_ok": not syntax_errors,
            "imports_ok": not warnings,
            "python_files_checked": python_files_checked,
            "errors": syntax_errors,
            "warnings": warnings,
        }

    def _finalize_validation(
        self,
        *,
        repo_root: Path,
        changed_files: list[str],
        validation: dict[str, Any],
        retries_used: int,
    ) -> dict[str, Any]:
        return {
            **self._validate_repository(repo_root, changed_files),
            **validation,
            "retries_used": retries_used,
        }

    def _validate_python_imports(
        self,
        *,
        tree: ast.AST,
        relative_path: str,
        repo_root: Path,
        edits: list[dict[str, Any]],
        local_module_roots: set[str],
    ) -> list[str]:
        collector = _PythonNameCollector()
        collector.visit(tree)

        warnings: list[str] = []
        undefined_names = sorted(
            name for name in collector.used_names if name not in collector.available_names and name not in BUILTIN_NAMES
        )
        if undefined_names:
            warnings.append(f"{relative_path}: possible missing import or undefined name(s): {', '.join(undefined_names)}")

        for module_name in collector.absolute_imports:
            top_level = module_name.split(".", 1)[0]
            if top_level not in local_module_roots:
                continue
            if not self._module_exists_locally(repo_root, module_name, edits):
                warnings.append(f"{relative_path}: possible invalid local import '{module_name}'")

        return warnings

    @staticmethod
    def _format_syntax_error(relative_path: str, exc: SyntaxError) -> str:
        line = exc.lineno or 0
        offset = exc.offset or 0
        message = exc.msg or "invalid syntax"
        return f"{relative_path}: syntax error at line {line}, column {offset}: {message}"

    @staticmethod
    def _discover_local_module_roots(repo_root: Path, edits: list[dict[str, Any]]) -> set[str]:
        roots: set[str] = set()
        for file_path in repo_root.glob("*.py"):
            roots.add(file_path.stem)
        for directory in repo_root.iterdir():
            if directory.is_dir() and (directory / "__init__.py").exists():
                roots.add(directory.name)
        for edit in edits:
            path = Path(str(edit["file"]))
            parts = path.parts
            if not parts:
                continue
            if len(parts) == 1 and path.suffix == ".py":
                roots.add(path.stem)
            if len(parts) > 1 and parts[0]:
                roots.add(parts[0])
        return roots

    @staticmethod
    def _module_exists_locally(repo_root: Path, module_name: str, edits: list[dict[str, Any]]) -> bool:
        module_path = Path(*module_name.split("."))
        candidate_files = {
            Path(str(edit["file"])).as_posix()
            for edit in edits
        }
        module_file = module_path.with_suffix(".py").as_posix()
        package_file = (module_path / "__init__.py").as_posix()
        if module_file in candidate_files or package_file in candidate_files:
            return True
        return (repo_root / module_file).exists() or (repo_root / package_file).exists()

    def _maybe_run_tests(self, repo_root: Path, instruction: str, step_args: dict[str, Any]) -> dict[str, Any]:
        requested = bool(step_args.get("run_tests", False)) or bool(TEST_TRIGGER_PATTERN.search(instruction))
        if not requested:
            return self._empty_test_results()

        tests_present = (repo_root / "tests").exists() or any(repo_root.rglob("test_*.py"))
        if not tests_present:
            return {
                "executed": False,
                "passed": False,
                "failures": ["No tests detected."],
            }

        try:
            output = run_shell_command(["pytest", "-q"], cwd=str(repo_root))
        except FileNotFoundError:
            return {
                "executed": False,
                "passed": False,
                "failures": ["pytest is not available."],
            }
        except ToolExecutionError as exc:
            failures = [entry for entry in (exc.stderr.strip(), exc.stdout.strip()) if entry]
            return {
                "executed": True,
                "passed": False,
                "failures": failures or [f"pytest failed with exit code {exc.returncode}"],
            }

        return {
            "executed": True,
            "passed": True,
            "failures": [] if not output else [output],
        }

    @staticmethod
    def _validate_repository(repo_root: Path, changed_files: list[str]) -> dict[str, Any]:
        python_files = [file_name for file_name in changed_files if file_name.endswith(".py")]
        return {
            "retrieval_used": True,
            "python_files_changed": python_files,
            "changed_file_count": len(changed_files),
            "file_count": len(list_files(repo_root)),
        }

    @staticmethod
    def _validate_inputs(instruction: str, cwd: str, step_args: dict[str, Any]) -> None:
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValueError("coding instruction must be a non-empty string")
        if not isinstance(step_args, dict):
            raise ValueError("coding step args must be an object")
        repo_root = Path(cwd).expanduser().resolve()
        if not repo_root.exists() or not repo_root.is_dir():
            raise ValueError(f"coding repository root does not exist: {repo_root}")

    @staticmethod
    def _validate_result(result: CodingStepResult) -> None:
        if not isinstance(result.success, bool):
            raise ValueError("coding result success must be a bool")
        if not isinstance(result.changed_files, list):
            raise ValueError("coding result changed_files must be a list")
        if not isinstance(result.diffs, dict):
            raise ValueError("coding result diffs must be an object")
        if not isinstance(result.retrieved_files, list):
            raise ValueError("coding result retrieved_files must be a list")
        if not isinstance(result.validation, dict):
            raise ValueError("coding result validation must be an object")
        if not isinstance(result.actions, list):
            raise ValueError("coding result actions must be a list")
        if not isinstance(result.tool_calls, list):
            raise ValueError("coding result tool_calls must be a list")
        if not isinstance(result.model_response, str):
            raise ValueError("coding result model_response must be a string")
        if result.error is not None and not isinstance(result.error, str):
            raise ValueError("coding result error must be a string or null")
        if not isinstance(result.tests, dict):
            raise ValueError("coding result tests must be an object")

    @staticmethod
    def _empty_test_results() -> dict[str, Any]:
        return {
            "executed": False,
            "passed": False,
            "failures": [],
        }

    @staticmethod
    def _action_to_tool(action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        action_name = str(action["action"])
        if action_name == "create_file":
            return "create_file", {"path": str(action["file"]), "content": str(action["content"])}
        if action_name == "edit_file":
            return "update_file", {"path": str(action["file"]), "content": str(action["content"])}
        if action_name == "create_folder":
            return "create_folder", {"path": str(action["path"])}
        raise ValueError(f"unsupported coding action: {action_name}")

    @staticmethod
    def _action_display_path(action: dict[str, Any]) -> str | None:
        if "file" in action:
            return str(action["file"])
        if "path" in action:
            return str(action["path"])
        return None


class _PythonNameCollector(ast.NodeVisitor):
    """Collect imported, defined, and used names for lightweight static checks."""

    def __init__(self) -> None:
        self.defined_names: set[str] = set()
        self.imported_names: set[str] = set()
        self.used_names: set[str] = set()
        self.absolute_imports: set[str] = set()

    @property
    def available_names(self) -> set[str]:
        return self.defined_names | self.imported_names

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            imported_name = alias.asname or alias.name.split(".", 1)[0]
            self.imported_names.add(imported_name)
            self.absolute_imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            self.absolute_imports.add(node.module)
        for alias in node.names:
            imported_name = alias.asname or alias.name
            self.imported_names.add(imported_name)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.defined_names.add(node.name)
        for arg in node.args.posonlyargs + node.args.args + node.args.kwonlyargs:
            self.defined_names.add(arg.arg)
        if node.args.vararg is not None:
            self.defined_names.add(node.args.vararg.arg)
        if node.args.kwarg is not None:
            self.defined_names.add(node.args.kwarg.arg)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.defined_names.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._collect_target_names(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._collect_target_names(node.target)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._collect_target_names(node.target)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._collect_target_names(node.target)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._collect_target_names(item.optional_vars)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self.visit_With(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.used_names.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.defined_names.add(node.id)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name:
            self.defined_names.add(node.name)
        self.generic_visit(node)

    def _collect_target_names(self, node: ast.AST) -> None:
        if isinstance(node, ast.Name):
            self.defined_names.add(node.id)
            return
        if isinstance(node, (ast.Tuple, ast.List)):
            for element in node.elts:
                self._collect_target_names(element)

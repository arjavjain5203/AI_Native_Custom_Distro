"""Lightweight orchestrator model for intent classification."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from ai_core.core.session import SessionManager
from ai_core.models.manager import ModelManager, ModelManagerError
from ai_core.models.ollama import OllamaError


logger = logging.getLogger(__name__)

VALID_MODES = {"conversation", "execution"}
VALID_TASK_TYPES = {"planning", "coding", "analysis", "system"}
VALID_AGENTS = {"planning", "coding", "analysis"}
LOW_CONFIDENCE_THRESHOLD = 0.6


class Orchestrator:
    """Classify user input into interaction mode, task type, and agent."""

    def __init__(
        self,
        model_manager: ModelManager | None = None,
        timeout_seconds: float = 5.0,
        session_manager: SessionManager | None = None,
    ) -> None:
        self.model_manager = model_manager or ModelManager()
        self.timeout_seconds = timeout_seconds
        self.session_manager = session_manager

    def classify_input(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned = user_input.strip()
        context = self._merge_context(session_id, context or {})
        try:
            response = self.model_manager.run_role_model(
                "orchestrator",
                self._build_prompt(cleaned, context),
                timeout_seconds=self.timeout_seconds,
            )
            decision = self._normalize_decision(self._parse_and_validate_response(response), cleaned)
            self._record_session(session_id, cleaned, decision)
            logger.info("Orchestrator model decision: %s", decision)
            return decision
        except (ModelManagerError, OllamaError, TimeoutError, ValueError) as exc:
            logger.warning("Orchestrator fallback triggered: %s", exc)
            fallback = self.fallback_classification(cleaned, context, session_id=session_id)
            logger.info("Orchestrator fallback decision: %s", fallback)
            return fallback

    def _build_prompt(self, user_input: str, context: dict[str, Any]) -> str:
        recent_messages = context.get("recent_messages", [])
        current_task_state = context.get("current_task_state")
        related_tasks = self._related_tasks(context)
        return f"""
You are the lightweight orchestrator for a local AI-native operating environment.

Return valid JSON only.
Do not explain.
Do not use markdown.
Do not add extra keys.

Allowed values:
- mode: conversation | execution
- task_type: planning | coding | analysis | system
- agent: planning | coding | analysis

Use the prior context to detect continuation of the same task.
If the user says things like "continue", "now add", "modify this", "implement it", or "fix bug in login",
and the recent context indicates an active or evolving task, treat it as continuation instead of resetting the task.

Examples:
Input: Let's discuss my project idea
Output: {{"mode":"conversation","task_type":"planning","agent":"planning","confidence":0.92}}

Input: Add JWT authentication to this project
Output: {{"mode":"execution","task_type":"coding","agent":"coding","confidence":0.97}}

Context:
last_mode=conversation
last_task_type=planning
recent_messages=["Let's discuss my project idea"]
current_task_state={{"status":"conversation","task_type":"planning","agent":"planning","active_command":"Let's discuss my project idea"}}
Input: now create the structure
Output: {{"mode":"execution","task_type":"system","agent":"planning","confidence":0.95}}

Context:
last_mode=execution
last_task_type=planning
recent_messages=["create a project"]
current_task_state={{"status":"completed","task_type":"planning","agent":"planning","active_command":"create a project"}}
Input: implement it
Output: {{"mode":"execution","task_type":"coding","agent":"coding","confidence":0.94}}

Current context:
cwd={context.get("cwd")}
last_mode={context.get("last_mode")}
last_task_type={context.get("last_task_type")}
last_agent={context.get("last_agent")}
recent_messages={recent_messages}
current_task_state={current_task_state}
related_tasks={related_tasks}

User input:
{user_input}
""".strip()

    def _parse_and_validate_response(self, response: str) -> dict[str, Any]:
        payload = json.loads(response)
        if not isinstance(payload, dict):
            raise ValueError("orchestrator response must be a JSON object")

        mode = payload.get("mode")
        task_type = payload.get("task_type")
        agent = payload.get("agent")
        confidence = payload.get("confidence")

        if mode not in VALID_MODES:
            raise ValueError(f"invalid orchestrator mode: {mode}")
        if task_type not in VALID_TASK_TYPES:
            raise ValueError(f"invalid orchestrator task_type: {task_type}")
        if agent not in VALID_AGENTS:
            raise ValueError(f"invalid orchestrator agent: {agent}")
        if not isinstance(confidence, (int, float)):
            raise ValueError("orchestrator confidence must be numeric")
        confidence_value = float(confidence)
        if not 0.0 <= confidence_value <= 1.0:
            raise ValueError("orchestrator confidence must be between 0 and 1")

        return {
            "mode": mode,
            "task_type": task_type,
            "agent": agent,
            "confidence": confidence_value,
        }

    def fallback_classification(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        merged_context = self._merge_context(session_id, context or {})
        decision = self._fallback_classification(user_input, merged_context)
        self._record_session(session_id, user_input.strip(), decision)
        return decision

    def preview_fallback_classification(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Return the fallback routing decision without mutating session state."""
        merged_context = self._merge_context(session_id, context or {})
        return self._fallback_classification(user_input.strip(), merged_context)

    def generate_conversation_response(
        self,
        user_input: str,
        context: dict[str, Any] | None = None,
        *,
        session_id: str | None = None,
    ) -> str:
        """Generate a natural-language conversation response without invoking planning."""
        cleaned = user_input.strip()
        merged_context = self._merge_context(session_id, context or {})
        try:
            response = self.model_manager.run_role_model(
                "orchestrator",
                self._build_conversation_prompt(cleaned, merged_context),
                timeout_seconds=self.timeout_seconds,
            )
            if not isinstance(response, str) or not response.strip():
                raise ValueError("conversation response must be a non-empty string")
            return response.strip()
        except (ModelManagerError, OllamaError, TimeoutError, ValueError) as exc:
            logger.warning("Conversation fallback triggered: %s", exc)
            return self._fallback_conversation_response(cleaned)

    def _fallback_classification(self, user_input: str, context: dict[str, Any]) -> dict[str, Any]:
        lowered = user_input.lower()
        last_mode = str(context.get("last_mode") or "").lower()
        last_task_type = str(context.get("last_task_type") or "").lower()
        last_agent = str(context.get("last_agent") or "").lower()
        related_tasks = self._related_tasks(context)
        current_task_state = self._current_task_state(context)
        current_status = str(current_task_state.get("status", "")).lower()
        current_task_type = str(current_task_state.get("task_type", "")).lower()
        current_agent = str(current_task_state.get("agent", "")).lower()
        continuation = self._looks_like_continuation(lowered)

        if continuation:
            continued = self._continuation_decision(
                lowered,
                last_mode=last_mode,
                last_task_type=last_task_type,
                last_agent=last_agent,
                current_status=current_status,
                current_task_type=current_task_type,
                current_agent=current_agent,
                context=context,
            )
            if continued is not None:
                return continued

        if last_mode == "conversation" and not self._looks_like_execution_trigger(lowered):
            return {
                "mode": "conversation",
                "task_type": "planning",
                "agent": "planning",
                "confidence": 0.72,
            }

        if self._looks_like_conversation(lowered):
            return {
                "mode": "conversation",
                "task_type": "planning",
                "agent": "planning",
                "confidence": 0.65,
            }

        if self._looks_like_analysis(lowered):
            return {
                "mode": "execution",
                "task_type": "analysis",
                "agent": "analysis",
                "confidence": 0.78,
            }

        if self._looks_like_coding(lowered):
            return {
                "mode": "execution",
                "task_type": "coding",
                "agent": "coding",
                "confidence": 0.8,
            }

        if self._looks_like_system(lowered):
            return {
                "mode": "execution",
                "task_type": "system",
                "agent": "planning",
                "confidence": 0.82,
            }

        if related_tasks and self._looks_like_similarity_request(lowered):
            if self._looks_like_analysis(lowered):
                return {
                    "mode": "execution",
                    "task_type": "analysis",
                    "agent": "analysis",
                    "confidence": 0.76,
                }
            if self._looks_like_coding(lowered) or self._looks_like_implementation(lowered):
                return {
                    "mode": "execution",
                    "task_type": "coding",
                    "agent": "coding",
                    "confidence": 0.79,
                }
            if self._looks_like_execution_trigger(lowered) or self._looks_like_system(lowered) or self._looks_like_project_request(lowered):
                return {
                    "mode": "execution",
                    "task_type": "system",
                    "agent": "planning",
                    "confidence": 0.8,
                }

        if last_task_type == "coding" or last_agent == "coding":
            return {
                "mode": "execution",
                "task_type": "coding",
                "agent": "coding",
                "confidence": 0.62,
            }
        if last_task_type == "analysis" or last_agent == "analysis":
            return {
                "mode": "execution",
                "task_type": "analysis",
                "agent": "analysis",
                "confidence": 0.61,
            }

        cwd = str(context.get("cwd", "")).lower()
        if "repo" in cwd or "project" in cwd:
            return {
                "mode": "execution",
                "task_type": "coding",
                "agent": "coding",
                "confidence": 0.58,
            }

        return {
            "mode": "execution" if self._looks_like_execution_trigger(lowered) else "conversation",
            "task_type": "planning",
            "agent": "planning",
            "confidence": 0.55 if not self._looks_like_execution_trigger(lowered) else 0.57,
        }

    def _build_conversation_prompt(self, user_input: str, context: dict[str, Any]) -> str:
        recent_messages = context.get("recent_messages", [])
        current_task_state = context.get("current_task_state")
        return f"""
You are the conversation interface for a local AI-native operating environment.

Respond in plain text only.
Do not return JSON.
Do not mention planners, tools, or pipelines.
Be concise and helpful.
If the user is greeting you, greet them back naturally.
If the user asks a general question, answer it directly.
If the user is vague, ask one clarifying question.

Current context:
cwd={context.get("cwd")}
last_mode={context.get("last_mode")}
last_task_type={context.get("last_task_type")}
last_agent={context.get("last_agent")}
recent_messages={recent_messages}
current_task_state={current_task_state}

User input:
{user_input}
""".strip()

    @staticmethod
    def _normalize_decision(decision: dict[str, Any], user_input: str) -> dict[str, Any]:
        if float(decision.get("confidence", 0.0)) >= LOW_CONFIDENCE_THRESHOLD:
            return decision
        return {
            "mode": "conversation",
            "task_type": "planning",
            "agent": "planning",
            "confidence": float(decision.get("confidence", 0.0)),
        }

    @staticmethod
    def _fallback_conversation_response(user_input: str) -> str:
        lowered = " ".join(user_input.lower().split())
        if lowered in {"hi", "hello", "hey", "hii", "yo"}:
            return "Hello. How can I help you today?"
        if re.search(r"\bhow are you\b", lowered):
            return "I'm doing well. How can I help you today?"
        if re.search(r"\bwhat is python\b|\bpython\?\b", lowered):
            return "Python is a high-level programming language used for automation, web development, data work, and AI."
        return "I can help with questions or tasks. Tell me what you want to understand or what you want me to do."

    def _merge_context(self, session_id: str | None, context: dict[str, Any]) -> dict[str, Any]:
        merged = {}
        if session_id is not None and self.session_manager is not None:
            merged.update(self.session_manager.get_context(session_id))
        merged.update(context)
        return merged

    def _record_session(self, session_id: str | None, user_input: str, decision: dict[str, Any]) -> None:
        if session_id is None or self.session_manager is None:
            return
        self.session_manager.update(
            session_id,
            user_input,
            mode=str(decision["mode"]),
            task_type=str(decision["task_type"]),
            agent=str(decision["agent"]),
            current_task_state=self._decision_task_state(user_input, decision),
        )

    @staticmethod
    def _decision_task_state(user_input: str, decision: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "conversation" if str(decision["mode"]) == "conversation" else "execution",
            "task_type": str(decision["task_type"]),
            "agent": str(decision["agent"]),
            "active_command": user_input,
        }

    @staticmethod
    def _current_task_state(context: dict[str, Any]) -> dict[str, Any]:
        current_task_state = context.get("current_task_state")
        if isinstance(current_task_state, dict):
            return current_task_state
        return {}

    @staticmethod
    def _related_tasks(context: dict[str, Any]) -> list[dict[str, str]]:
        related_tasks = context.get("related_tasks")
        if not isinstance(related_tasks, list):
            return []

        normalized: list[dict[str, str]] = []
        for item in related_tasks:
            if not isinstance(item, dict):
                continue
            task_id = item.get("task_id")
            summary = item.get("summary")
            if not isinstance(task_id, str) or not task_id.strip():
                continue
            if not isinstance(summary, str) or not summary.strip():
                continue
            normalized.append({"task_id": task_id.strip(), "summary": summary.strip()})
        return normalized[:3]

    def _continuation_decision(
        self,
        text: str,
        *,
        last_mode: str,
        last_task_type: str,
        last_agent: str,
        current_status: str,
        current_task_type: str,
        current_agent: str,
        context: dict[str, Any],
    ) -> dict[str, Any] | None:
        has_context = any(
            [
                last_mode,
                last_task_type,
                last_agent,
                current_status,
                current_task_type,
                current_agent,
                context.get("recent_messages"),
            ]
        )
        if not has_context:
            return None

        if last_mode == "conversation":
            if self._looks_like_system(text):
                return {
                    "mode": "execution",
                    "task_type": "system",
                    "agent": "planning",
                    "confidence": 0.84,
                }
            if self._looks_like_execution_trigger(text) or self._looks_like_coding(text) or self._looks_like_implementation(text):
                return {
                    "mode": "execution",
                    "task_type": "coding",
                    "agent": "coding",
                    "confidence": 0.83,
                }
            return {
                "mode": "conversation",
                "task_type": "planning",
                "agent": "planning",
                "confidence": 0.74,
            }

        if self._looks_like_analysis(text) and not self._looks_like_coding(text):
            return {
                "mode": "execution",
                "task_type": "analysis",
                "agent": "analysis",
                "confidence": 0.79,
            }

        if self._looks_like_system(text) and not self._looks_like_coding(text):
            return {
                "mode": "execution",
                "task_type": "system",
                "agent": "planning",
                "confidence": 0.82,
            }

        if (
            self._looks_like_coding(text)
            or self._looks_like_implementation(text)
            or self._looks_like_bugfix_follow_up(text)
            or current_task_type == "coding"
            or current_agent == "coding"
            or last_task_type == "coding"
            or last_agent == "coding"
        ):
            return {
                "mode": "execution",
                "task_type": "coding",
                "agent": "coding",
                "confidence": 0.81,
            }

        if current_task_type == "analysis" or current_agent == "analysis" or last_task_type == "analysis" or last_agent == "analysis":
            return {
                "mode": "execution",
                "task_type": "analysis",
                "agent": "analysis",
                "confidence": 0.72,
            }

        if current_task_type == "system" or last_task_type == "system":
            return {
                "mode": "execution",
                "task_type": "system",
                "agent": "planning",
                "confidence": 0.7,
            }

        if current_task_type == "planning" or last_task_type == "planning":
            if self._looks_like_execution_trigger(text) or self._looks_like_implementation(text):
                return {
                    "mode": "execution",
                    "task_type": "coding",
                    "agent": "coding",
                    "confidence": 0.76,
                }
            return {
                "mode": "conversation",
                "task_type": "planning",
                "agent": "planning",
                "confidence": 0.68,
            }

        return None

    @staticmethod
    def _looks_like_conversation(text: str) -> bool:
        return bool(
            re.search(
                r"\b(discuss|brainstorm|idea|plan|thinking about|talk about|want to build)\b",
                text,
            )
        )

    @staticmethod
    def _looks_like_coding(text: str) -> bool:
        return bool(
            re.search(
                r"(?:\b(add|modify|edit|refactor|fix|update|implement|write)\b.*\b(code|project|repo|authentication|auth|jwt|endpoint|api|file|login|bug|app|application|fastapi)\b)|(?:\b(create|build)\b.*\b(app|application|fastapi|endpoint|api|code)\b)",
                text,
            )
        )

    @staticmethod
    def _looks_like_implementation(text: str) -> bool:
        return bool(
            re.search(
                r"\b(implement it|build it|do it|apply it|add auth|add authentication|wire it up)\b",
                text,
            )
        )

    @staticmethod
    def _looks_like_analysis(text: str) -> bool:
        return bool(
            re.search(
                r"\b(debug|diagnose|analyze|explain|inspect|investigate)\b|\b(error|logs|failure|traceback|issue)\b",
                text,
            )
        )

    @staticmethod
    def _looks_like_system(text: str) -> bool:
        return bool(
            re.search(
                r"\b(create folder|create file|list files|show files|project structure|structure|install|package|pacman|docker|git|clone|branch|push|service|systemctl)\b",
                text,
            )
        )

    @staticmethod
    def _looks_like_continuation(text: str) -> bool:
        return bool(
            re.search(
                r"\b(continue|keep going|go on|next|then|now|after that|follow up|implement it|modify this|update this|fix bug|now add|add authentication|add auth)\b",
                text,
            )
        )

    @staticmethod
    def _looks_like_bugfix_follow_up(text: str) -> bool:
        return bool(re.search(r"\b(fix|patch|resolve)\b.*\b(bug|issue|login|auth|endpoint|api)\b", text))

    @staticmethod
    def _looks_like_similarity_request(text: str) -> bool:
        return bool(
            re.search(
                r"\b(similar|same setup|like before|same as last time|previous task|previous setup|same project)\b",
                text,
            )
        )

    @staticmethod
    def _looks_like_project_request(text: str) -> bool:
        return bool(re.search(r"\b(project|setup|app|structure|scaffold)\b", text))

    @staticmethod
    def _looks_like_execution_trigger(text: str) -> bool:
        return bool(
            re.search(
                r"\b(now|go ahead|start|create|build|implement|run|execute|apply|make|add)\b",
                text,
            )
        )

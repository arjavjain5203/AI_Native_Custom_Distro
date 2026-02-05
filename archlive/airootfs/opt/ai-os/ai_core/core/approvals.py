"""Approval state for risky actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import secrets
from typing import Any
from uuid import uuid4

from ai_core.core.types import ApprovalRequest, ExecutionState, PlanStep


@dataclass(slots=True)
class PendingApproval:
    """Paused task state waiting for user confirmation."""

    approval: ApprovalRequest
    state: ExecutionState
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def command(self) -> str:
        return self.state.command

    @property
    def cwd(self) -> str:
        return self.state.cwd

    @property
    def steps(self) -> list[PlanStep]:
        return self.state.steps

    @property
    def step_index(self) -> int:
        return self.state.step_index

    @property
    def step_results(self) -> list[dict[str, Any]]:
        return self.state.step_results


class ApprovalStore:
    """In-memory approval tracker for the daemon runtime."""

    def __init__(self, ttl_seconds: int = 300) -> None:
        self.ttl = timedelta(seconds=ttl_seconds)
        self._requests: dict[str, PendingApproval] = {}

    def create(
        self,
        *,
        state: ExecutionState,
    ) -> ApprovalRequest:
        self._expire_stale()
        step = state.steps[state.step_index]
        approval = ApprovalRequest(
            approval_id=f"approval-{uuid4().hex[:8]}",
            token=secrets.token_urlsafe(16),
            task_id=state.task_id,
            step_index=state.step_index,
            category=step.approval_category or "general",
            prompt=f"Approve step '{step.description}'?",
        )
        self._requests[approval.approval_id] = PendingApproval(
            approval=approval,
            state=ExecutionState(
                task_id=state.task_id,
                command=state.command,
                cwd=state.cwd,
                steps=list(state.steps),
                step_index=state.step_index,
                step_results=list(state.step_results),
                files_modified=list(state.files_modified),
                steps_completed=list(state.steps_completed),
                errors=list(state.errors),
                routing=dict(state.routing),
                planning_metadata=dict(state.planning_metadata),
                context=dict(state.context),
                status=state.status,
            ),
        )
        return approval

    def get(self, approval_id: str) -> PendingApproval | None:
        self._expire_stale()
        return self._requests.get(approval_id)

    def consume(self, approval_id: str, token: str) -> PendingApproval:
        self._expire_stale()
        pending = self._requests.get(approval_id)
        if pending is None:
            raise ValueError(f"approval not found: {approval_id}")
        if pending.approval.token != token:
            raise ValueError("invalid approval token")
        del self._requests[approval_id]
        return pending

    def reject(self, approval_id: str, token: str) -> PendingApproval:
        return self.consume(approval_id, token)

    def _expire_stale(self) -> None:
        now = datetime.now(UTC)
        expired = [
            approval_id
            for approval_id, pending in self._requests.items()
            if now - pending.created_at > self.ttl
        ]
        for approval_id in expired:
            del self._requests[approval_id]

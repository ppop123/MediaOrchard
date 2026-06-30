from __future__ import annotations

from datetime import UTC, datetime

from mediaorchard.controller.db.models import Step
from mediaorchard.shared.enums import StepStatus


class TransitionError(ValueError):
    """Raised when a state transition or assignment fence is invalid."""


LEGAL_STEP_TRANSITIONS: dict[StepStatus, set[StepStatus]] = {
    StepStatus.PENDING: {StepStatus.QUEUED, StepStatus.SKIPPED, StepStatus.CANCELLED},
    StepStatus.QUEUED: {StepStatus.ASSIGNED, StepStatus.CANCELLED},
    StepStatus.ASSIGNED: {StepStatus.RUNNING, StepStatus.QUEUED, StepStatus.FAILED, StepStatus.CANCELLED},
    StepStatus.RUNNING: {StepStatus.COMPLETED, StepStatus.FAILED, StepStatus.CANCELLED},
    StepStatus.FAILED: {StepStatus.QUEUED},
    StepStatus.SKIPPED: set(),
    StepStatus.CANCELLED: set(),
    StepStatus.COMPLETED: set(),
}


def transition_step(current: StepStatus, target: StepStatus) -> StepStatus:
    current = StepStatus(current)
    target = StepStatus(target)
    if target not in LEGAL_STEP_TRANSITIONS[current]:
        raise TransitionError(f"invalid step transition: {current} -> {target}")
    return target


def assign_step(step: Step, node_id: str, now: datetime | None = None) -> Step:
    now = now or datetime.now(UTC)
    step.status = transition_step(step.status, StepStatus.ASSIGNED)
    step.assigned_node_id = node_id
    step.assigned_at = now
    step.assignment_epoch += 1
    return step


def validate_assignment_epoch(step: Step, assignment_epoch: int) -> None:
    if step.assignment_epoch != assignment_epoch:
        raise TransitionError(
            f"stale assignment epoch: expected {step.assignment_epoch}, got {assignment_epoch}"
        )


def recover_timed_out_step(step: Step) -> Step:
    if step.status == StepStatus.ASSIGNED:
        step.status = transition_step(step.status, StepStatus.QUEUED)
        step.assigned_node_id = None
        step.assigned_at = None
        step.error_message = "worker_heartbeat_timeout"
        step.assignment_epoch += 1
        return step

    if step.status == StepStatus.RUNNING:
        step.error_message = "worker_heartbeat_timeout"
        step.assigned_node_id = None
        step.assigned_at = None
        step.retry_count += 1
        step.assignment_epoch += 1
        step.status = transition_step(step.status, StepStatus.FAILED)
        if step.retry_count <= step.max_retries:
            step.status = transition_step(step.status, StepStatus.QUEUED)
        return step

    raise TransitionError(f"cannot recover timed-out step from {step.status}")

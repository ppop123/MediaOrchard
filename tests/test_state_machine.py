from datetime import UTC, datetime

import pytest

from mediaorchard.controller.db.models import Step
from mediaorchard.controller.runtime.state_machine import (
    TransitionError,
    assign_step,
    recover_timed_out_step,
    transition_step,
    validate_assignment_epoch,
)
from mediaorchard.shared.enums import StepStatus


def test_step_transition_rejects_invalid_jump():
    with pytest.raises(TransitionError):
        transition_step(StepStatus.PENDING, StepStatus.RUNNING)


def test_assign_step_sets_node_timestamp_and_epoch():
    step = Step(
        job_id="job_1",
        plan_id="plan_1",
        step_type="probe_media",
        tool_name="probe_media",
        status=StepStatus.QUEUED,
    )
    now = datetime(2026, 6, 30, tzinfo=UTC)

    assign_step(step, node_id="mac-studio", now=now)

    assert step.status == StepStatus.ASSIGNED
    assert step.assigned_node_id == "mac-studio"
    assert step.assigned_at == now
    assert step.assignment_epoch == 1


def test_assignment_epoch_rejects_late_worker_completion():
    step = Step(
        job_id="job_1",
        plan_id="plan_1",
        step_type="probe_media",
        tool_name="probe_media",
        assignment_epoch=3,
    )

    validate_assignment_epoch(step, 3)

    with pytest.raises(TransitionError):
        validate_assignment_epoch(step, 2)


def test_recover_assigned_step_requeues_without_consuming_retry():
    step = Step(
        job_id="job_1",
        plan_id="plan_1",
        step_type="probe_media",
        tool_name="probe_media",
        status=StepStatus.ASSIGNED,
        assigned_node_id="mac-studio",
        assignment_epoch=4,
    )

    recover_timed_out_step(step)

    assert step.status == StepStatus.QUEUED
    assert step.assigned_node_id is None
    assert step.error_message == "worker_heartbeat_timeout"
    assert step.retry_count == 0
    assert step.assignment_epoch == 5


def test_recover_running_step_fails_then_requeues_when_retry_available():
    step = Step(
        job_id="job_1",
        plan_id="plan_1",
        step_type="probe_media",
        tool_name="probe_media",
        status=StepStatus.RUNNING,
        assigned_node_id="mac-studio",
        retry_count=0,
        max_retries=2,
        assignment_epoch=1,
    )

    recover_timed_out_step(step)

    assert step.status == StepStatus.QUEUED
    assert step.assigned_node_id is None
    assert step.error_message == "worker_heartbeat_timeout"
    assert step.retry_count == 1
    assert step.assignment_epoch == 2

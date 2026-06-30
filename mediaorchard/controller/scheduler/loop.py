from __future__ import annotations

from datetime import datetime

from mediaorchard.controller.db.models import Node, Step
from mediaorchard.controller.runtime.state_machine import assign_step
from mediaorchard.controller.scheduler.policies import SchedulerConfig
from mediaorchard.controller.scheduler.policies import is_ffmpeg_step, is_whisper_step
from mediaorchard.controller.scheduler.scoring import SchedulerDecision, select_node_for_step
from mediaorchard.shared.enums import StepStatus


class SchedulerError(ValueError):
    """Raised when scheduler assignment preconditions are violated."""


def assign_best_node(
    step: Step,
    nodes: list[Node],
    config: SchedulerConfig,
    *,
    now: datetime,
) -> SchedulerDecision:
    if step.status != StepStatus.QUEUED:
        raise SchedulerError(f"cannot assign step in status {step.status}")

    decision = select_node_for_step(step, nodes, config, now=now)
    if decision.selected_node is not None:
        assign_step(step, decision.selected_node.id, now=now)
        decision.selected_node.active_jobs += 1
        if is_whisper_step(step):
            decision.selected_node.active_whisper_jobs += 1
        elif is_ffmpeg_step(step):
            decision.selected_node.active_ffmpeg_jobs += 1
    return decision

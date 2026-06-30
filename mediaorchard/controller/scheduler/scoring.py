from __future__ import annotations

from dataclasses import dataclass

from mediaorchard.controller.db.models import Node, Step
from mediaorchard.controller.scheduler.policies import (
    SchedulerConfig,
    is_ffmpeg_step,
    is_node_eligible,
    is_whisper_step,
)


@dataclass(frozen=True)
class NodeCost:
    total: float
    components: dict[str, float]


@dataclass(frozen=True)
class SchedulerDecision:
    selected_node: Node | None
    rejected_nodes: dict[str, str]
    score_breakdown: dict[str, dict[str, float]]
    reason: str


def same_type_active_jobs(step: Step, node: Node) -> float:
    if is_whisper_step(step):
        return float(node.active_whisper_jobs)
    if is_ffmpeg_step(step):
        return float(node.active_ffmpeg_jobs)
    return float(node.active_jobs)


def thermal_penalty(node: Node) -> float:
    # serious/critical are hard-filtered before scoring; values remain here for
    # explainability if future policy allows them with a high penalty.
    return {
        "normal": 0.0,
        "fair": 20.0,
        "serious": 100.0,
        "critical": 100.0,
    }.get(node.thermal_state, 10.0)


def calculate_node_cost(step: Step, node: Node, config: SchedulerConfig) -> NodeCost:
    components = {
        "cpu_load": 0.30 * node.cpu_percent,
        "memory_pressure": 0.20 * node.memory_percent,
        "active_same_type_jobs": 0.15 * same_type_active_jobs(step, node),
        "thermal_penalty": 0.10 * thermal_penalty(node),
        "disk_io_penalty": 0.0,
        "recent_usage_penalty": 0.0,
        "file_locality_bonus": 0.0,
        "benchmark_speed_bonus": 0.0,
    }
    total = (
        components["cpu_load"]
        + components["memory_pressure"]
        + components["active_same_type_jobs"]
        + components["thermal_penalty"]
        + components["disk_io_penalty"]
        + components["recent_usage_penalty"]
        - components["file_locality_bonus"]
        - components["benchmark_speed_bonus"]
    )
    components["total"] = total
    return NodeCost(total=total, components=components)


def select_node_for_step(
    step: Step,
    nodes: list[Node],
    config: SchedulerConfig,
    *,
    now,
) -> SchedulerDecision:
    rejected: dict[str, str] = {}
    scores: dict[str, dict[str, float]] = {}
    candidates: list[tuple[float, Node]] = []

    for node in nodes:
        eligibility = is_node_eligible(step, node, config, now=now)
        if not eligibility.eligible:
            rejected[node.id] = eligibility.reason
            continue
        cost = calculate_node_cost(step, node, config)
        scores[node.id] = cost.components
        candidates.append((cost.total, node))

    if not candidates:
        return SchedulerDecision(None, rejected, scores, "no_eligible_nodes")

    candidates.sort(key=lambda item: (item[0], item[1].id))
    selected = candidates[0][1]
    return SchedulerDecision(selected, rejected, scores, f"selected:{selected.id}")

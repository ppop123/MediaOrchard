from datetime import UTC, datetime, timedelta

import pytest

from mediaorchard.controller.db.models import Node, Step
from mediaorchard.controller.scheduler.loop import SchedulerError, assign_best_node
from mediaorchard.controller.scheduler.policies import SchedulerConfig, is_node_eligible
from mediaorchard.controller.scheduler.scoring import calculate_node_cost, select_node_for_step
from mediaorchard.shared.enums import NodeStatus, StepStatus


NOW = datetime(2026, 6, 30, 12, 0, tzinfo=UTC)


def make_node(**overrides):
    data = {
        "id": "mac-studio",
        "name": "Mac Studio",
        "status": NodeStatus.ONLINE,
        "shared_root": "/Volumes/MediaOrchard",
        "cpu_percent": 20.0,
        "memory_percent": 30.0,
        "free_disk_gb": 200.0,
        "thermal_state": "normal",
        "on_battery": False,
        "active_jobs": 0,
        "active_ffmpeg_jobs": 0,
        "active_whisper_jobs": 0,
        "max_ffmpeg_jobs": 2,
        "max_whisper_jobs": 1,
        "last_heartbeat_at": NOW,
    }
    data.update(overrides)
    return Node(**data)


def make_step(**overrides):
    data = {
        "job_id": "job_1",
        "plan_id": "plan_1",
        "step_type": "transcribe_audio",
        "tool_name": "transcribe_audio",
        "status": StepStatus.QUEUED,
    }
    data.update(overrides)
    return Step(**data)


@pytest.mark.parametrize(
    ("node_overrides", "reason"),
    [
        ({"status": NodeStatus.OFFLINE}, "node_offline"),
        ({"last_heartbeat_at": NOW - timedelta(seconds=31)}, "heartbeat_expired"),
        ({"shared_root": "/Volumes/Other"}, "shared_root_mismatch"),
        ({"cpu_percent": 90.0}, "cpu_too_high"),
        ({"memory_percent": 90.0}, "memory_too_high"),
        ({"free_disk_gb": 10.0}, "disk_too_low"),
        ({"thermal_state": "serious"}, "thermal_blocked"),
        ({"active_whisper_jobs": 1, "max_whisper_jobs": 1}, "whisper_concurrency_full"),
    ],
)
def test_node_hard_filters_return_reason(node_overrides, reason):
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(**node_overrides)
    step = make_step()

    result = is_node_eligible(step, node, config, now=NOW)

    assert result.eligible is False
    assert result.reason == reason


def test_avoid_nodes_constraint_blocks_node():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(id="macbook-pro")
    step = make_step(input_json={"constraints": {"avoid_nodes": ["macbook-pro"]}})

    result = is_node_eligible(step, node, config, now=NOW)

    assert result.eligible is False
    assert result.reason == "node_avoided"


def test_battery_runtime_constraint_blocks_long_work():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(on_battery=True)
    step = make_step(input_json={"estimated_runtime_minutes": 25})

    result = is_node_eligible(step, node, config, now=NOW)

    assert result.eligible is False
    assert result.reason == "battery_runtime_blocked"


def test_ffmpeg_concurrency_is_separate_from_whisper():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(active_ffmpeg_jobs=2, max_ffmpeg_jobs=2)
    step = make_step(step_type="extract_audio", tool_name="extract_audio")

    result = is_node_eligible(step, node, config, now=NOW)

    assert result.eligible is False
    assert result.reason == "ffmpeg_concurrency_full"


def test_whisper_substring_does_not_classify_unknown_tool_as_whisper():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(active_whisper_jobs=1, max_whisper_jobs=1)
    step = make_step(step_type="custom", tool_name="not_a_whisper_tool")

    result = is_node_eligible(step, node, config, now=NOW)

    assert result.eligible is True


def test_heartbeat_boundary_is_not_expired_at_exact_timeout():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(last_heartbeat_at=NOW - timedelta(seconds=30))
    step = make_step()

    result = is_node_eligible(step, node, config, now=NOW)

    assert result.eligible is True


def test_naive_now_is_normalized_for_heartbeat_check():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    node = make_node(last_heartbeat_at=NOW.replace(tzinfo=None))
    step = make_step()

    result = is_node_eligible(step, node, config, now=NOW.replace(tzinfo=None))

    assert result.eligible is True


def test_calculate_node_cost_prefers_lower_load_node():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step()
    low = make_node(id="low", cpu_percent=10, memory_percent=20, active_whisper_jobs=0)
    high = make_node(id="high", cpu_percent=70, memory_percent=80, active_whisper_jobs=0)

    assert calculate_node_cost(step, low, config).total < calculate_node_cost(step, high, config).total


def test_unknown_step_cost_uses_generic_active_jobs_not_ffmpeg_jobs():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step(step_type="custom", tool_name="custom_tool")
    node = make_node(active_jobs=3, active_ffmpeg_jobs=50, active_whisper_jobs=50)

    cost = calculate_node_cost(step, node, config)

    assert cost.components["active_same_type_jobs"] == 0.15 * 3


def test_select_node_returns_lowest_cost_eligible_node_and_rejections():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step()
    low = make_node(id="low", cpu_percent=10, memory_percent=20)
    high = make_node(id="high", cpu_percent=60, memory_percent=70)
    blocked = make_node(id="blocked", cpu_percent=95)

    decision = select_node_for_step(step, [blocked, high, low], config, now=NOW)

    assert decision.selected_node == low
    assert decision.rejected_nodes["blocked"] == "cpu_too_high"
    assert decision.score_breakdown["low"]["total"] < decision.score_breakdown["high"]["total"]


def test_select_node_prefers_higher_priority_host_over_lower_load_local_node():
    config = SchedulerConfig(
        shared_root="/Volumes/MediaOrchard",
        node_priorities={"192.168.50.8": 100},
    )
    step = make_step()
    local = make_node(id="local", host="127.0.0.1", cpu_percent=5, memory_percent=5)
    remote = make_node(id="mac-mini", host="192.168.50.8", cpu_percent=60, memory_percent=60)

    decision = select_node_for_step(step, [local, remote], config, now=NOW)

    assert decision.selected_node == remote
    assert decision.score_breakdown["mac-mini"]["priority_bonus"] == 100.0
    assert decision.score_breakdown["local"]["priority_bonus"] == 0.0


def test_select_node_priority_can_match_node_id_when_host_is_unavailable():
    config = SchedulerConfig(
        shared_root="/Volumes/MediaOrchard",
        node_priorities={"192.168.50.9": 100},
    )
    step = make_step()
    local = make_node(id="local", host=None, cpu_percent=5, memory_percent=5)
    remote = make_node(id="192.168.50.9", host=None, cpu_percent=60, memory_percent=60)

    decision = select_node_for_step(step, [local, remote], config, now=NOW)

    assert decision.selected_node == remote


def test_node_priority_does_not_override_hard_filters():
    config = SchedulerConfig(
        shared_root="/Volumes/MediaOrchard",
        node_priorities={"192.168.50.8": 100},
    )
    step = make_step()
    local = make_node(id="local", cpu_percent=10, memory_percent=10)
    overloaded_remote = make_node(id="mac-mini", host="192.168.50.8", cpu_percent=95, memory_percent=10)

    decision = select_node_for_step(step, [overloaded_remote, local], config, now=NOW)

    assert decision.selected_node == local
    assert decision.rejected_nodes["mac-mini"] == "cpu_too_high"


def test_select_node_tie_breaks_by_node_id():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step()
    b_node = make_node(id="b-node")
    a_node = make_node(id="a-node")

    decision = select_node_for_step(step, [b_node, a_node], config, now=NOW)

    assert decision.selected_node == a_node


def test_assign_best_node_leaves_step_queued_when_no_node_is_eligible():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step()
    blocked = make_node(id="blocked", cpu_percent=95)

    decision = assign_best_node(step, [blocked], config, now=NOW)

    assert decision.selected_node is None
    assert step.status == StepStatus.QUEUED
    assert step.assigned_node_id is None
    assert step.assignment_epoch == 0


def test_assign_best_node_moves_step_to_assigned_with_epoch():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step()
    node = make_node(id="mac-mini")

    decision = assign_best_node(step, [node], config, now=NOW)

    assert decision.selected_node == node
    assert step.status == StepStatus.ASSIGNED
    assert step.assigned_node_id == "mac-mini"
    assert step.assignment_epoch == 1
    assert step.assigned_at == NOW


def test_assign_best_node_rejects_non_queued_step():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step(status=StepStatus.RUNNING)
    node = make_node(id="mac-mini")

    with pytest.raises(SchedulerError):
        assign_best_node(step, [node], config, now=NOW)


def test_assign_best_node_increments_active_counts_for_selected_node():
    config = SchedulerConfig(shared_root="/Volumes/MediaOrchard")
    step = make_step()
    node = make_node(id="mac-mini", active_jobs=1, active_whisper_jobs=0)

    assign_best_node(step, [node], config, now=NOW)

    assert node.active_jobs == 2
    assert node.active_whisper_jobs == 1

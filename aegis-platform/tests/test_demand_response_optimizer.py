import pytest

pytest.importorskip("ortools")

from optimizer import DRParticipant, optimize_demand_response


def test_infeasible_request_allocates_no_more_than_available_capacity():
    participants = [
        DRParticipant("site-a", max_curtailment_kw=10.0, comfort_penalty=1.0),
        DRParticipant("site-b", max_curtailment_kw=20.0, comfort_penalty=2.0),
    ]

    result = optimize_demand_response(participants, required_total_kw=100.0)

    assert result.feasible is False
    assert result.total_allocated_kw == 30.0
    assert [s.allocated_curtailment_kw for s in result.schedules] == [10.0, 20.0]
    assert "INFEASIBLE" in result.status_message


def test_invalid_participant_bounds_are_rejected():
    participants = [
        DRParticipant("bad-site", max_curtailment_kw=5.0, min_curtailment_kw=10.0),
    ]

    with pytest.raises(ValueError, match="min_curtailment_kw"):
        optimize_demand_response(participants, required_total_kw=3.0)


def test_optimizer_prefers_lower_comfort_penalty_when_feasible():
    participants = [
        DRParticipant("expensive", max_curtailment_kw=20.0, comfort_penalty=10.0),
        DRParticipant("cheap", max_curtailment_kw=20.0, comfort_penalty=1.0),
    ]

    result = optimize_demand_response(participants, required_total_kw=10.0)

    allocations = {s.participant_id: s.allocated_curtailment_kw for s in result.schedules}
    assert result.feasible is True
    assert allocations["cheap"] == 10.0
    assert allocations["expensive"] == 0.0


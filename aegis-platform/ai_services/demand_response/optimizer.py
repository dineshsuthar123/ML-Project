"""
AEGIS – Demand Response Optimizer
====================================
Uses Google OR-Tools CP-SAT solver to allocate load curtailment
across participants given:
  - required_total_kw : aggregate curtailment target (from forecaster / operator)
  - participants       : list of flexible loads with max_curtailment and comfort_penalty

Returns an optimal dispatch schedule that minimizes total discomfort.

Reference:
  OR-Tools CP-SAT: https://developers.google.com/optimization/reference/python/sat/python/cp_model
"""

from dataclasses import dataclass, field
from typing import Optional
from ortools.sat.python import cp_model


@dataclass
class DRParticipant:
    """A flexible load that can participate in demand response."""
    participant_id:     str
    max_curtailment_kw: float     # maximum power reduction allowed
    min_curtailment_kw: float = 0.0
    comfort_penalty:    float = 1.0   # $/kW – higher = participant prefers not to curtail
    baseline_load_kw:   float = 0.0   # current load (for context)
    accepted:           bool  = False


@dataclass
class DRSchedule:
    participant_id:        str
    allocated_curtailment_kw: float
    accepted:              bool
    comfort_cost:          float


@dataclass
class DRResult:
    total_allocated_kw:   float
    total_required_kw:    float
    schedules:            list[DRSchedule]
    total_comfort_cost:   float
    feasible:             bool
    status_message:       str


def optimize_demand_response(
    participants: list[DRParticipant],
    required_total_kw: float,
    scale: int = 100,   # integer precision: 1 unit = 1/scale kW
) -> DRResult:
    """
    Solve the demand response dispatch problem via CP-SAT.

    Objective: minimize total comfort_penalty × curtailment_kw
    Subject to:
        sum(curtailment_kw_i) >= required_total_kw
        min_curtailment_kw_i <= curtailment_kw_i <= max_curtailment_kw_i   for each i

    Parameters
    ----------
    participants       : list of DRParticipant objects
    required_total_kw  : total curtailment needed (kW)
    scale              : integer scaling factor for CP-SAT

    Returns
    -------
    DRResult with per-participant allocations
    """
    model  = cp_model.CpModel()
    solver = cp_model.CpSolver()

    n = len(participants)
    if n == 0 or required_total_kw <= 0:
        return DRResult(
            total_allocated_kw=0.0,
            total_required_kw=required_total_kw,
            schedules=[],
            total_comfort_cost=0.0,
            feasible=True,
            status_message="No action required",
        )

    for p in participants:
        if p.min_curtailment_kw < 0 or p.max_curtailment_kw < 0:
            raise ValueError("Curtailment bounds must be non-negative")
        if p.min_curtailment_kw > p.max_curtailment_kw:
            raise ValueError(
                f"min_curtailment_kw exceeds max_curtailment_kw for {p.participant_id}"
            )

    # Decision variables: curtailment in integer units (kW * scale)
    vars_ = []
    for p in participants:
        lb = int(p.min_curtailment_kw * scale)
        ub = int(p.max_curtailment_kw * scale)
        v  = model.NewIntVar(lb, ub, f"curtail_{p.participant_id}")
        vars_.append(v)

    # Constraint: total >= required
    required_int = int(required_total_kw * scale)
    model.Add(sum(vars_) >= required_int)

    # Objective: minimize sum(penalty_i * curtailment_i)
    # Scale penalties to integers (multiply by 1000 for precision)
    penalty_scale = 1000
    obj_terms = [
        int(p.comfort_penalty * penalty_scale) * v
        for p, v in zip(participants, vars_)
    ]
    model.Minimize(sum(obj_terms))

    # Solve with time limit
    solver.parameters.max_time_in_seconds = 5.0
    status = solver.Solve(model)

    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    schedules = []
    total_allocated = 0.0
    total_cost      = 0.0

    for p, v in zip(participants, vars_):
        if feasible:
            alloc_kw = solver.Value(v) / scale
        else:
            # Proportional fallback, capped by each participant's actual capability.
            total_max = sum(q.max_curtailment_kw for q in participants) or 1.0
            alloc_kw  = min(
                p.max_curtailment_kw,
                p.max_curtailment_kw / total_max * required_total_kw,
            )

        cost = alloc_kw * p.comfort_penalty
        schedules.append(DRSchedule(
            participant_id           = p.participant_id,
            allocated_curtailment_kw = round(alloc_kw, 2),
            accepted                 = alloc_kw > 0.0,
            comfort_cost             = round(cost, 4),
        ))
        total_allocated += alloc_kw
        total_cost      += cost

    return DRResult(
        total_allocated_kw  = round(total_allocated, 2),
        total_required_kw   = required_total_kw,
        schedules           = schedules,
        total_comfort_cost  = round(total_cost, 4),
        feasible            = feasible,
        status_message      = solver.StatusName(status) if feasible else "INFEASIBLE - maximum available curtailment allocated",
    )


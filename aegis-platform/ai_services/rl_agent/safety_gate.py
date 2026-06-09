"""
AEGIS – RL Agent Safety Gate
==============================
Middleware that MUST be called before any control signal is dispatched.
Enforces hard physical constraints and overrides unsafe actions with
a safe fallback (do nothing / reduce power).

Constraints checked:
  1. Battery SoC in [SOC_MIN, SOC_MAX]
  2. Voltage within [V_MIN, V_MAX] pu
  3. Rate-of-change limit (max delta SoC per step)
"""

from dataclasses import dataclass


SOC_MIN         = 0.20    # 20 %
SOC_MAX         = 0.90    # 90 %
VOLTAGE_MIN     = 0.95    # pu
VOLTAGE_MAX     = 1.05    # pu
MAX_SOC_DELTA   = 0.05    # max SoC change per 1-min step (rate of change)


@dataclass
class SafetyCheckResult:
    approved:        bool
    final_action:    float   # possibly overridden
    violations:      list[str]
    override_reason: str = ""


def apply_safety_gate(
    action:     float,
    soc:        float,
    voltage_pu: float = 1.0,
    prev_soc:   float | None = None,
) -> SafetyCheckResult:
    """
    Evaluate safety constraints and return an approved/overridden action.

    Parameters
    ----------
    action     : proposed action in [-1, 1]
                 positive = charge, negative = discharge
    soc        : current battery state of charge [0, 1]
    voltage_pu : current grid voltage in per-unit
    prev_soc   : SoC at previous step (for rate-of-change check)

    Returns
    -------
    SafetyCheckResult
    """
    violations = []
    final      = action

    # ── 1. Voltage check ────────────────────────────────
    if voltage_pu < VOLTAGE_MIN:
        violations.append(f"UNDERVOLTAGE: {voltage_pu:.3f} pu < {VOLTAGE_MIN}")
        # Force discharge to support voltage (inject power)
        final = min(final, -0.3)

    if voltage_pu > VOLTAGE_MAX:
        violations.append(f"OVERVOLTAGE: {voltage_pu:.3f} pu > {VOLTAGE_MAX}")
        # Force charge to absorb excess power
        final = max(final, 0.3)

    # ── 2. SoC bounds ────────────────────────────────────
    if soc <= SOC_MIN and final < 0:
        violations.append(f"SOC_LOW: {soc:.3f} ≤ {SOC_MIN}, block discharge")
        final = 0.0

    if soc >= SOC_MAX and final > 0:
        violations.append(f"SOC_HIGH: {soc:.3f} ≥ {SOC_MAX}, block charge")
        final = 0.0

    # ── 3. Rate-of-change limit ──────────────────────────
    if prev_soc is not None:
        delta = abs(soc - prev_soc)
        if delta > MAX_SOC_DELTA:
            violations.append(f"RAMP_LIMIT: delta_SoC={delta:.4f} > {MAX_SOC_DELTA}")
            # Scale action down
            scale = MAX_SOC_DELTA / delta if delta > 0 else 1.0
            final = final * min(scale, 1.0)

    final    = float(max(-1.0, min(1.0, final)))
    approved = len(violations) == 0

    return SafetyCheckResult(
        approved        = approved,
        final_action    = final,
        violations      = violations,
        override_reason = "; ".join(violations) if violations else "OK",
    )


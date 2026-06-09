"""
AEGIS – Anomaly Detection: Causal Rule Engine
===============================================
Given an anomaly alert and recent telemetry context, provides a
structured diagnosis / root-cause hypothesis.

Rules are expressed as a priority-ordered list of (condition, diagnosis)
pairs evaluated against a feature snapshot.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AnomalyContext:
    """Snapshot of features at the time of anomaly detection."""
    node_id:          str
    reconstruction_error: float
    voltage_pu:       float   = 1.0
    frequency_hz:     float   = 50.0
    load_kw:          float   = 0.0
    solar_kw:         float   = 0.0
    battery_soc:      float   = 0.5
    temperature:      float   = 25.0
    load_mean_15m:    float   = 0.0
    load_std_15m:     float   = 0.0
    recent_alerts:    int     = 0    # number of alerts in last 5 minutes


@dataclass
class Diagnosis:
    severity:   str               # LOW / MEDIUM / HIGH / CRITICAL
    code:       str               # machine-readable code
    description: str
    recommended_action: str
    confidence: float = 0.0       # 0-1


# ── Rule definitions ─────────────────────────────────────────

RULES: list[tuple] = [
    # (condition_fn, diagnosis)
    (
        lambda c: c.voltage_pu < 0.90,
        Diagnosis("CRITICAL", "UNDERVOLTAGE",
                  "Voltage below 0.90 pu – possible transformer overload or cable fault.",
                  "Activate reactive power compensation; check feeder loads.", 0.95)
    ),
    (
        lambda c: c.voltage_pu > 1.10,
        Diagnosis("HIGH", "OVERVOLTAGE",
                  "Voltage above 1.10 pu – possible excess solar injection or load shedding.",
                  "Curtail solar inverters; increase reactive power absorption.", 0.90)
    ),
    (
        lambda c: abs(c.frequency_hz - 50.0) > 0.5,
        Diagnosis("CRITICAL", "FREQUENCY_DEVIATION",
                  f"Frequency deviation > 0.5 Hz – generation/load imbalance.",
                  "Deploy primary frequency response; check generation dispatch.", 0.97)
    ),
    (
        lambda c: c.load_kw > c.load_mean_15m + 3 * c.load_std_15m and c.load_std_15m > 0,
        Diagnosis("HIGH", "LOAD_SPIKE",
                  "Load significantly above 15-min rolling mean – unexpected demand surge.",
                  "Activate demand response program; alert operator.", 0.85)
    ),
    (
        lambda c: c.battery_soc < 0.15,
        Diagnosis("HIGH", "BATTERY_DEPLETED",
                  "Battery SoC below 15% – risk of blackout if grid disconnected.",
                  "Stop discharging; initiate emergency charging from grid.", 0.92)
    ),
    (
        lambda c: c.battery_soc > 0.92,
        Diagnosis("MEDIUM", "BATTERY_OVERCHARGE",
                  "Battery SoC above 92% – curtail charging to avoid overcharge.",
                  "Reduce charging rate; consider export to grid.", 0.80)
    ),
    (
        lambda c: c.solar_kw > 0 and c.load_kw < c.solar_kw * 0.3,
        Diagnosis("MEDIUM", "REVERSE_POWER_FLOW",
                  "Solar generation >> load – possible reverse power flow on LV feeder.",
                  "Monitor transformer tap; consider curtailment or battery charge.", 0.78)
    ),
    (
        lambda c: c.recent_alerts >= 3,
        Diagnosis("HIGH", "CASCADING_FAULT",
                  "Multiple anomalies detected in short window – possible cascading failure.",
                  "Switch to islanded mode; notify grid operator immediately.", 0.88)
    ),
]

FALLBACK = Diagnosis(
    "LOW", "UNKNOWN_ANOMALY",
    "Reconstruction error exceeds threshold but no specific rule matched.",
    "Monitor closely; collect data for offline diagnosis.", 0.50
)


def diagnose(ctx: AnomalyContext) -> Diagnosis:
    """
    Evaluate rules in priority order; return the first matching diagnosis.
    Falls back to UNKNOWN_ANOMALY if no rule matches.
    """
    for condition, diag in RULES:
        try:
            if condition(ctx):
                return diag
        except Exception:
            continue
    return FALLBACK


def severity_level(severity: str) -> int:
    return {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}.get(severity, 0)


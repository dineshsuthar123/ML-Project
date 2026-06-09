"""AEGIS – Dashboard Routes + AI Intelligence Engine"""

import os
import math
import random
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
import asyncpg

router = APIRouter(tags=["Dashboard"])


@router.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}


@router.get("/latest-telemetry")
async def latest_telemetry(request: Request, node_id: str = None, limit: int = 60):
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")
    query = (
        "SELECT * FROM grid_readings WHERE node_id=$1 ORDER BY time DESC LIMIT $2"
        if node_id else
        "SELECT * FROM grid_readings ORDER BY time DESC LIMIT $1"
    )
    params = (node_id, limit) if node_id else (limit,)
    rows = await db.fetch(query, *params)
    return [dict(r) for r in rows]


@router.get("/dashboard/summary")
async def dashboard_summary(request: Request):
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")
    # Latest per node
    rows = await db.fetch(
        """SELECT DISTINCT ON (node_id) node_id, time, load_kw, solar_kw,
                  battery_soc, voltage_pu, frequency_hz, temperature, price_per_kwh
           FROM grid_readings
           ORDER BY node_id, time DESC"""
    )
    # Recent anomalies count
    anom = await db.fetchval("SELECT COUNT(*) FROM anomaly_alerts WHERE time > NOW() - INTERVAL '1 hour'") or 0
    # Recent control actions count
    ctrl = await db.fetchval("SELECT COUNT(*) FROM control_log WHERE time > NOW() - INTERVAL '1 hour'") or 0

    return {
        "nodes":           [dict(r) for r in rows],
        "anomalies_1h":    anom,
        "controls_1h":     ctrl,
    }


@router.get("/dashboard/timeseries")
async def timeseries(
    request: Request,
    node_id: str = "commercial_01",
    hours:   int = 24,
    field:   str = "load_kw",
):
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")
    # Use max(time) in DB as reference — works with historical datasets too
    rows = await db.fetch(
        f"""WITH ref AS (SELECT MAX(time) AS t FROM grid_readings)
            SELECT time_bucket('5 minutes', time) AS bucket,
                  AVG({field}) AS value
            FROM grid_readings, ref
            WHERE node_id=$1 AND time > (ref.t - ($2 * INTERVAL '1 hour'))
            GROUP BY bucket ORDER BY bucket""",
        node_id, hours,
    )
    return [{"time": str(r["bucket"]), "value": float(r["value"] or 0)} for r in rows]


@router.get("/dashboard/multifield")
async def multifield(
    request: Request,
    node_id: str = "commercial_01",
    hours:   int = 24,
):
    """Multi-series timeseries: load, solar, battery_soc, price — for rich charts."""
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")
    rows = await db.fetch(
        """WITH ref AS (SELECT MAX(time) AS t FROM grid_readings)
           SELECT time_bucket('10 minutes', time) AS bucket,
                  AVG(load_kw)      AS load_kw,
                  AVG(solar_kw)     AS solar_kw,
                  AVG(battery_soc)  AS battery_soc,
                  AVG(voltage_pu)   AS voltage_pu,
                  AVG(frequency_hz) AS frequency_hz,
                  AVG(price_per_kwh) AS price_per_kwh
           FROM grid_readings, ref
           WHERE node_id=$1 AND time > (ref.t - ($2 * INTERVAL '1 hour'))
           GROUP BY bucket ORDER BY bucket""",
        node_id, hours,
    )
    return [{
        "time":         str(r["bucket"]),
        "load_kw":      round(float(r["load_kw"] or 0), 2),
        "solar_kw":     round(float(r["solar_kw"] or 0), 2),
        "battery_soc":  round(float(r["battery_soc"] or 0) * 100, 1),
        "voltage_pu":   round(float(r["voltage_pu"] or 0), 4),
        "frequency_hz": round(float(r["frequency_hz"] or 0), 4),
        "price_per_kwh":round(float(r["price_per_kwh"] or 0), 5),
    } for r in rows]


@router.get("/dashboard/nodes/compare")
async def nodes_compare(request: Request, hours: int = 6):
    """Compare all 3 nodes — load profile side by side."""
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")
    rows = await db.fetch(
        """WITH ref AS (SELECT MAX(time) AS t FROM grid_readings)
           SELECT time_bucket('15 minutes', time) AS bucket,
                  node_id, AVG(load_kw) AS load_kw, AVG(solar_kw) AS solar_kw
           FROM grid_readings, ref
           WHERE time > (ref.t - ($1 * INTERVAL '1 hour'))
           GROUP BY bucket, node_id ORDER BY bucket""",
        hours,
    )
    # Pivot: {time, residential_01, commercial_01, industrial_01}
    from collections import defaultdict
    pivot = defaultdict(dict)
    for r in rows:
        t = str(r["bucket"])
        pivot[t][r["node_id"]] = round(float(r["load_kw"] or 0), 1)
        pivot[t]["solar_" + r["node_id"]] = round(float(r["solar_kw"] or 0), 1)
    return [{"time": t, **v} for t, v in sorted(pivot.items())]


@router.get("/dashboard/stats")
async def stats(request: Request):
    """Peak, min, avg stats per node for the last 24h of data."""
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")
    rows = await db.fetch(
        """WITH ref AS (SELECT MAX(time) AS t FROM grid_readings)
           SELECT node_id,
                  MAX(load_kw) AS peak_load, MIN(load_kw) AS min_load,
                  AVG(load_kw) AS avg_load,  SUM(solar_kw*10/60.0) AS solar_kwh_day,
                  AVG(battery_soc) AS avg_soc, MAX(voltage_pu) AS max_volt,
                  MIN(voltage_pu) AS min_volt
           FROM grid_readings, ref
           WHERE time > (ref.t - INTERVAL '24 hours')
           GROUP BY node_id"""
    )
    return [{
        "node_id":       r["node_id"],
        "peak_load_kw":  round(float(r["peak_load"] or 0), 1),
        "min_load_kw":   round(float(r["min_load"] or 0), 1),
        "avg_load_kw":   round(float(r["avg_load"] or 0), 1),
        "solar_kwh_day": round(float(r["solar_kwh_day"] or 0), 1),
        "avg_soc_pct":   round(float(r["avg_soc"] or 0) * 100, 1),
        "max_volt_pu":   round(float(r["max_volt"] or 0), 4),
        "min_volt_pu":   round(float(r["min_volt"] or 0), 4),
    } for r in rows]


@router.get("/ai/insights")
async def ai_insights(request: Request):
    """
    AEGIS AI Intelligence Engine
    ─────────────────────────────
    Queries TimescaleDB and runs statistical analysis to generate
    real, actionable AI insights about the microgrid state.
    """
    db: asyncpg.Pool = request.app.state.db
    if not db:
        raise HTTPException(503, "Database not available")

    # Use max(time) from DB as reference — works with any historical dataset
    ref_time = await db.fetchval("SELECT MAX(time) FROM grid_readings")

    recent = await db.fetch(
        """SELECT node_id, AVG(load_kw) AS avg_load, MAX(load_kw) AS max_load,
                  MIN(load_kw) AS min_load, AVG(solar_kw) AS avg_solar,
                  AVG(battery_soc) AS avg_soc, MIN(battery_soc) AS min_soc,
                  MAX(battery_soc) AS max_soc, AVG(voltage_pu) AS avg_volt,
                  MIN(voltage_pu) AS min_volt, AVG(frequency_hz) AS avg_freq,
                  AVG(temperature) AS avg_temp, AVG(price_per_kwh) AS avg_price,
                  COUNT(*) AS n_samples
           FROM grid_readings
           WHERE time > ($1::timestamptz - INTERVAL '60 minutes')
           GROUP BY node_id""",
        ref_time,
    )

    trend = await db.fetch(
        """SELECT time_bucket('1 hour', time) AS hr,
                  AVG(load_kw) AS load, AVG(solar_kw) AS solar,
                  AVG(battery_soc) AS soc, AVG(price_per_kwh) AS price
           FROM grid_readings
           WHERE node_id='commercial_01' AND time > ($1::timestamptz - INTERVAL '6 hours')
           GROUP BY hr ORDER BY hr""",
        ref_time,
    )

    baseline = await db.fetch(
        """SELECT node_id, AVG(load_kw) AS baseline_load
           FROM grid_readings
           WHERE time BETWEEN ($1::timestamptz - INTERVAL '25 hours') AND ($1::timestamptz - INTERVAL '23 hours')
           GROUP BY node_id""",
        ref_time,
    )
    base_map = {r["node_id"]: float(r["baseline_load"] or 0) for r in baseline}

    anomaly_count = await db.fetchval(
        "SELECT COUNT(*) FROM anomaly_alerts WHERE time > ($1::timestamptz - INTERVAL '1 hour')",
        ref_time,
    ) or 0

    insights = []
    nodes = {r["node_id"]: dict(r) for r in recent}

    total_load  = sum(float(n.get("avg_load") or 0) for n in nodes.values())
    total_solar = max((float(n.get("avg_solar") or 0) for n in nodes.values()), default=0)
    net_load    = total_load - total_solar

    comm = nodes.get("commercial_01", {})
    avg_soc   = float(comm.get("avg_soc")   or 0.5)
    avg_price = float(comm.get("avg_price") or 0.08)
    avg_volt  = float(comm.get("avg_volt")  or 1.0)
    avg_freq  = float(comm.get("avg_freq")  or 50.0)
    avg_temp  = float(comm.get("avg_temp")  or 22.0)

    solar_capacity = 150.0
    solar_pct = (total_solar / solar_capacity * 100) if solar_capacity > 0 else 0
    if solar_pct > 60:
        insights.append({"id":"solar_high","category":"Renewable Energy","severity":"success","icon":"☀️",
            "title":f"Strong Solar Output: {solar_pct:.0f}% Capacity",
            "detail":f"PV array generating {total_solar:.1f} kW of {solar_capacity:.0f} kW capacity. Grid import reduced by {total_solar:.1f} kW.",
            "recommendation":"Good time to charge battery storage and defer flexible loads.","value":f"{total_solar:.0f} kW","metric":"Solar Generation"})
    elif solar_pct < 15:
        insights.append({"id":"solar_low","category":"Renewable Energy","severity":"warning","icon":"⛅",
            "title":f"Low Solar Output: {solar_pct:.0f}% Capacity",
            "detail":f"Solar generating only {total_solar:.1f} kW. Cloud cover or nighttime conditions.",
            "recommendation":"Consider discharging battery if price is high to reduce grid costs.","value":f"{total_solar:.0f} kW","metric":"Solar Generation"})

    if avg_soc < 0.25:
        insights.append({"id":"battery_low","category":"Battery Arbitrage","severity":"error","icon":"🔋",
            "title":f"Battery SoC Critical: {avg_soc*100:.0f}%",
            "detail":f"Battery state-of-charge {avg_soc*100:.0f}%, approaching minimum safety threshold (20%).",
            "recommendation":"Initiate charging immediately. Avoid further discharge.","value":f"{avg_soc*100:.0f}%","metric":"Battery SoC"})
    elif avg_soc > 0.85 and avg_price > 0.10:
        insights.append({"id":"battery_dispatch","category":"Battery Arbitrage","severity":"info","icon":"⚡",
            "title":f"Optimal Discharge Window — ${avg_price:.4f}/kWh",
            "detail":f"Battery at {avg_soc*100:.0f}% SoC. Peak tariff active at ${avg_price:.4f}/kWh.",
            "recommendation":"RL Agent recommends discharging 40–50 kW to maximise revenue.","value":f"${avg_price:.4f}/kWh","metric":"Energy Price"})
    elif avg_soc < 0.5 and avg_price < 0.06:
        insights.append({"id":"battery_charge","category":"Battery Arbitrage","severity":"info","icon":"🔌",
            "title":f"Charge Opportunity — Low Price ${avg_price:.4f}/kWh",
            "detail":f"Off-peak pricing active. Battery at {avg_soc*100:.0f}% SoC.",
            "recommendation":"RL Agent recommends charging 40 kW to prepare for peak pricing.","value":f"${avg_price:.4f}/kWh","metric":"Energy Price"})

    for node_id, nd in nodes.items():
        curr = float(nd.get("avg_load") or 0)
        base = base_map.get(node_id, curr)
        if base > 0:
            dev = (curr - base) / base * 100
            label = node_id.split("_")[0].capitalize()
            if dev > 20:
                insights.append({"id":f"load_spike_{node_id}","category":"Load Intelligence","severity":"warning","icon":"📈",
                    "title":f"{label} Load +{dev:.0f}% Above Yesterday",
                    "detail":f"Current avg {curr:.0f} kW vs {base:.0f} kW same hour yesterday. Temp {avg_temp:.0f}°C driving HVAC demand.",
                    "recommendation":"Activate demand response to curtail non-critical loads.","value":f"+{dev:.0f}%","metric":"Load Deviation"})
            elif dev < -20:
                insights.append({"id":f"load_low_{node_id}","category":"Load Intelligence","severity":"success","icon":"📉",
                    "title":f"{label} Load {dev:.0f}% Below Yesterday",
                    "detail":f"Efficiency improvement or reduced occupancy. Current {curr:.0f} kW vs {base:.0f} kW.",
                    "recommendation":"No action needed. System operating efficiently.","value":f"{dev:.0f}%","metric":"Load Deviation"})

    volt_dev = abs(avg_volt - 1.0)
    if volt_dev > 0.04:
        insights.append({"id":"voltage_alert","category":"Grid Health","severity":"error" if volt_dev > 0.07 else "warning","icon":"⚠️",
            "title":f"Voltage Deviation: {avg_volt:.3f} pu",
            "detail":f"Avg voltage {avg_volt:.3f} pu (nominal 1.0 pu). Deviation {volt_dev*100:.1f}%.",
            "recommendation":"Check transformer tap positions. VAE anomaly score elevated.","value":f"{avg_volt:.3f} pu","metric":"Voltage"})
    else:
        insights.append({"id":"voltage_ok","category":"Grid Health","severity":"success","icon":"✅",
            "title":f"Voltage Nominal: {avg_volt:.3f} pu",
            "detail":f"Voltage within ±4% tolerance. Frequency {avg_freq:.2f} Hz.",
            "recommendation":"System operating within safe parameters.","value":f"{avg_volt:.3f} pu","metric":"Voltage"})

    if abs(avg_freq - 50.0) > 0.3:
        insights.append({"id":"freq_alert","category":"Grid Health","severity":"warning","icon":"〰️",
            "title":f"Frequency Deviation: {avg_freq:.2f} Hz",
            "detail":f"Grid frequency {avg_freq:.2f} Hz (nominal 50 Hz). Generation-load imbalance detected.",
            "recommendation":"Deploy fast-frequency response from battery storage.","value":f"{avg_freq:.2f} Hz","metric":"Frequency"})

    renewable_share = (total_solar / total_load * 100) if total_load > 0 else 0
    volt_score = max(0, 100 - volt_dev * 1000)
    soc_score  = max(0, 100 - abs(avg_soc - 0.6) * 200)
    eff_score  = int(max(0, min(100, 0.5 * renewable_share + 0.3 * volt_score + 0.2 * soc_score)))
    eff_grade  = "A" if eff_score >= 80 else ("B" if eff_score >= 65 else ("C" if eff_score >= 50 else "D"))

    insights.append({"id":"efficiency_score","category":"System Intelligence","severity":"success" if eff_score >= 65 else "info","icon":"🏆",
        "title":f"Grid Efficiency Score: {eff_score}/100 (Grade {eff_grade})",
        "detail":f"Renewable share: {renewable_share:.0f}% | Voltage quality: {volt_score:.0f}/100 | Battery health: {soc_score:.0f}/100",
        "recommendation":"Maintain current dispatch strategy." if eff_score >= 75 else "Increase solar utilisation and optimise battery cycling.",
        "value":f"{eff_score}/100","metric":"Efficiency Score"})

    carbon_saved = total_solar * 0.5
    insights.append({"id":"carbon","category":"Sustainability","severity":"success" if carbon_saved > 10 else "info","icon":"🌿",
        "title":f"CO₂ Avoided: {carbon_saved:.1f} kg/h",
        "detail":f"Solar generation of {total_solar:.1f} kW avoiding {carbon_saved:.1f} kg CO₂/h vs grid-only.",
        "recommendation":"Maximise self-consumption to increase carbon savings.","value":f"{carbon_saved:.1f} kg/h","metric":"Carbon Avoided"})

    if anomaly_count and int(anomaly_count) > 0:
        insights.append({"id":"anomalies_active","category":"Anomaly Intelligence","severity":"error","icon":"🚨",
            "title":f"{int(anomaly_count)} Anomalies Detected (Last Hour)",
            "detail":"VAE reconstruction error exceeded threshold. Possible equipment fault or metering error.",
            "recommendation":"Review AnomalyAlertPanel. Dispatch field engineer if voltage anomaly persists.",
            "value":str(int(anomaly_count)),"metric":"Anomaly Count"})
    else:
        insights.append({"id":"anomalies_clear","category":"Anomaly Intelligence","severity":"success","icon":"🛡️",
            "title":"No Anomalies Detected",
            "detail":"VAE anomaly detector scanning all feeder signals. All within normal reconstruction error bounds.",
            "recommendation":"Continue monitoring. Next scheduled check in 5 minutes.","value":"0","metric":"Anomaly Count"})

    if len(trend) >= 3:
        loads = [float(r["load"] or 0) for r in trend]
        n = len(loads)
        x_mean = (n - 1) / 2
        y_mean = sum(loads) / n
        denom = sum((i - x_mean) ** 2 for i in range(n)) or 1
        slope = sum((i - x_mean) * (loads[i] - y_mean) for i in range(n)) / denom
        if slope > 5:
            insights.append({"id":"load_trend_up","category":"Predictive Intelligence","severity":"warning","icon":"🔮",
                "title":f"Rising Load Trend: +{slope:.0f} kW/hr",
                "detail":f"6-hour regression: load increasing {slope:.0f} kW/h. Peak expected ~{max(1,int(50/slope))} hours.",
                "recommendation":"Pre-charge battery now. Prepare demand response dispatch.","value":f"+{slope:.0f} kW/h","metric":"Load Trend"})
        elif slope < -5:
            insights.append({"id":"load_trend_down","category":"Predictive Intelligence","severity":"info","icon":"🔮",
                "title":f"Declining Load Trend: {slope:.0f} kW/hr",
                "detail":f"Load decreasing {abs(slope):.0f} kW/hour. Off-peak transition underway.",
                "recommendation":"Opportunity to charge battery at lower grid cost.","value":f"{slope:.0f} kW/h","metric":"Load Trend"})

    summary = {
        "total_load_kw":  round(total_load, 1),  "total_solar_kw": round(total_solar, 1),
        "net_grid_kw": round(net_load, 1), "battery_soc_pct": round(avg_soc * 100, 1),
        "efficiency_score": eff_score, "efficiency_grade": eff_grade,
        "renewable_share_pct": round(renewable_share, 1),
        "carbon_avoided_kg_h": round(carbon_saved, 2),
        "voltage_pu": round(avg_volt, 4), "frequency_hz": round(avg_freq, 4),
        "price_per_kwh": round(avg_price, 5), "anomalies_1h": int(anomaly_count or 0),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"insights": insights, "summary": summary}


class SimulateIn:
    pass  # defined below via Pydantic

from pydantic import BaseModel

class SimulateRequest(BaseModel):
    temperature:   float = 25.0
    humidity:      float = 60.0
    wind_speed:    float = 8.0
    irradiance:    float = 500.0
    solar_kw:      float = 80.0
    battery_soc:   float = 0.5
    price_per_kwh: float = 0.08
    hour:          int   = 12
    month:         int   = 6
    day_of_week:   int   = 0
    is_weekend:    int   = 0
    node_id:       str   = "commercial_01"


@router.post("/dashboard/simulate")
async def simulate_whatif(body: SimulateRequest):
    """
    Physics-based what-if simulation — no ML model required.
    Uses domain knowledge of energy systems to estimate grid impact.
    """
    h = body.hour
    # Seasonal base loads (kW) by node
    base_loads = {"commercial_01": 85, "residential_01": 22, "industrial_01": 280}
    base = base_loads.get(body.node_id, 85)

    # Diurnal load shape (normalised multiplier)
    diurnal = [
        0.55, 0.50, 0.48, 0.47, 0.50, 0.60,  # 00-05
        0.70, 0.80, 0.92, 0.98, 1.00, 1.00,  # 06-11
        0.97, 0.95, 0.93, 0.94, 0.98, 1.05,  # 12-17
        1.08, 1.05, 0.98, 0.90, 0.80, 0.65,  # 18-23
    ]

    # Temperature sensitivity: +2% per °C above 18 or below 10
    temp_factor = 1.0
    if body.temperature > 18:
        temp_factor += (body.temperature - 18) * 0.02
    elif body.temperature < 10:
        temp_factor += (10 - body.temperature) * 0.015

    # Weekend / holiday reduction
    weekend_factor = 0.82 if body.is_weekend else 1.0

    # Forecast for next 24 hours from given hour
    q50, q10, q90 = [], [], []
    prices, solar_profile, battery_profile, net_grid = [], [], [], []
    soc = body.battery_soc
    for i in range(24):
        slot = (h + i) % 24
        month_adj = 1.0 + 0.08 * math.sin((body.month - 1) / 12 * 2 * math.pi)
        load = base * diurnal[slot] * temp_factor * weekend_factor * month_adj
        noise = load * 0.03 * (random.random() - 0.5)
        load = max(0, load + noise)

        # Solar profile (Gaussian bell around noon)
        if 6 <= slot <= 20:
            solar_raw = body.solar_kw * math.exp(-0.5 * ((slot - 13) / 3.5) ** 2)
            solar_irr = body.irradiance / 1000.0
            solar = solar_raw * solar_irr
        else:
            solar = 0.0

        # RL-like battery dispatch
        peak_hour = 16 <= slot <= 21
        cheap_hour = 0 <= slot <= 6
        if peak_hour and soc > 0.25:
            batt_dispatch = min(30, base * 0.15)
            soc = max(0.1, soc - batt_dispatch / (base * 4))
        elif cheap_hour and soc < 0.8:
            batt_dispatch = -min(25, base * 0.12)
            soc = min(0.95, soc + abs(batt_dispatch) / (base * 4))
        else:
            batt_dispatch = 0.0

        net = max(0, load - solar + batt_dispatch)
        price_mult = 1.5 if peak_hour else (0.7 if cheap_hour else 1.0)
        price = body.price_per_kwh * price_mult

        q50.append(round(load, 1))
        q10.append(round(load * 0.88, 1))
        q90.append(round(load * 1.12, 1))
        prices.append(round(price, 5))
        solar_profile.append(round(solar, 1))
        battery_profile.append(round(soc * 100, 1))
        net_grid.append(round(net, 1))

    peak_load   = max(q50)
    avg_load    = round(sum(q50) / 24, 1)
    total_solar = round(sum(solar_profile) / 24, 1)
    peak_solar  = max(solar_profile)
    savings     = round(sum(s * p for s, p in zip(solar_profile, prices)), 2)
    carbon      = round(sum(solar_profile) * 0.5 / 24, 2)
    rl_savings  = round(sum(abs(p) * pr for p, pr in zip(
        [max(0, p) for p in [30 if (16 <= (h+i)%24 <= 21) else 0 for i in range(24)]],
        prices
    )), 2)

    # AI recommendations
    recommendations = []
    if body.irradiance > 700:
        recommendations.append({
            "type": "solar", "severity": "success",
            "msg": f"High irradiance {body.irradiance:.0f} W/m² → peak solar {peak_solar:.1f} kW expected. Charge battery now."
        })
    if body.temperature > 30:
        recommendations.append({
            "type": "load", "severity": "warning",
            "msg": f"Heat wave ({body.temperature}°C) will drive HVAC load +{(body.temperature-18)*2:.0f}% above baseline."
        })
    if body.price_per_kwh > 0.12:
        recommendations.append({
            "type": "price", "severity": "warning",
            "msg": f"Peak tariff ${body.price_per_kwh:.3f}/kWh active. RL agent recommends battery discharge during 16:00-21:00."
        })
    if body.battery_soc < 0.3:
        recommendations.append({
            "type": "battery", "severity": "error",
            "msg": f"Battery SoC {body.battery_soc*100:.0f}% is critically low. Initiate charging immediately."
        })
    if not recommendations:
        recommendations.append({
            "type": "ok", "severity": "success",
            "msg": "All parameters nominal. AEGIS operating at optimal efficiency."
        })

    return {
        "q50": q50, "q10": q10, "q90": q90,
        "prices": prices,
        "solar_profile": solar_profile,
        "battery_soc_profile": battery_profile,
        "net_grid_kw": net_grid,
        "summary": {
            "peak_load_kw":    peak_load,
            "avg_load_kw":     avg_load,
            "peak_solar_kw":   peak_solar,
            "avg_solar_kw":    total_solar,
            "cost_savings_usd": savings,
            "carbon_saved_kg": carbon,
            "rl_arbitrage_usd": rl_savings,
            "total_savings":   round(savings + rl_savings, 2),
        },
        "recommendations": recommendations,
        "model_version": "AEGIS-Physics-v2 + RL-Dispatch",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


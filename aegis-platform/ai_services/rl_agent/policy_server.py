"""
AEGIS – RL Agent Policy Server
================================
FastAPI service that:
  • Loads trained SAC policy on startup (from artifacts/ or MinIO).
  • POST /act  – returns safe action given current microgrid state.
  • POST /explain – returns SHAP feature importance for the action.
  • Publishes approved actions to Kafka `rl.actions`.
  • GET  /health
  • GET  /metrics – Prometheus
"""

import os
import json
import logging
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from confluent_kafka import Producer

from safety_gate import apply_safety_gate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rl-policy-server")

ARTIFACT_DIR    = os.getenv("ARTIFACT_DIR", "artifacts")
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
APP_ENV         = os.getenv("APP_ENV", "development").lower()
DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if APP_ENV == "production" and "*" in origins:
        raise RuntimeError("CORS_ALLOW_ORIGINS must not include '*' in production")
    return origins

_policy    = None
_db_pool: Optional[asyncpg.Pool] = None
_producer: Optional[Producer]   = None
_prev_soc: dict[str, float]     = {}   # per-node SoC history for rate-of-change


def _load_policy():
    global _policy
    model_path = Path(ARTIFACT_DIR) / "best_model.zip"
    if not model_path.exists():
        model_path = Path(ARTIFACT_DIR) / "sac_final.zip"
    if model_path.exists():
        from stable_baselines3 import SAC
        _policy = SAC.load(str(model_path))
        log.info("SAC policy loaded from %s", model_path)
    else:
        log.warning("No trained SAC policy found. /act will use rule-based fallback.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool, _producer
    _load_policy()
    try:
        _db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=3)
    except Exception as exc:
        log.warning("DB unavailable: %s", exc)
    _producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    log.info("RL Policy server ready.")
    yield
    if _db_pool:
        await _db_pool.close()
    if _producer:
        _producer.flush()


app = FastAPI(title="AEGIS RL Agent", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


# ── Schemas ──────────────────────────────────────────────────

class StateRequest(BaseModel):
    battery_soc:  float = Field(0.5,  ge=0.0, le=1.0)
    load_kw:      float = Field(200.0, ge=0.0)
    solar_kw:     float = Field(50.0,  ge=0.0)
    price_per_kwh: float = Field(0.08, ge=0.0)
    voltage_pu:   float = Field(1.0)
    hour:         int   = Field(12, ge=0, le=23)
    node_id:      str   = Field("commercial_01")


class ActionResponse(BaseModel):
    node_id:         str
    raw_action:      float
    safe_action:     float
    approved:        bool
    violations:      list[str]
    override_reason: str
    description:     str   # human-readable charge/discharge description


# ── Helpers ──────────────────────────────────────────────────

def _build_obs(req: StateRequest) -> np.ndarray:
    import math
    MAX_LOAD_KW  = 1200.0
    MAX_SOLAR_KW = 150.0
    MAX_PRICE    = 0.20
    return np.array([
        req.battery_soc * 2 - 1,
        req.load_kw   / MAX_LOAD_KW  * 2 - 1,
        req.solar_kw  / MAX_SOLAR_KW * 2 - 1,
        req.price_per_kwh / MAX_PRICE * 2 - 1,
        math.sin(2 * math.pi * req.hour / 24),
        math.cos(2 * math.pi * req.hour / 24),
    ], dtype=np.float32)


def _rule_based_action(req: StateRequest) -> float:
    """Simple heuristic when no RL model is loaded."""
    hour = req.hour
    if req.price_per_kwh > 0.10 and req.battery_soc > 0.30:
        return -0.8   # discharge at peak price
    elif req.price_per_kwh < 0.05 and req.battery_soc < 0.80:
        return 0.8    # charge at off-peak
    elif req.solar_kw > req.load_kw * 0.8 and req.battery_soc < 0.85:
        return 0.5    # charge from excess solar
    return 0.0


def _describe_action(action: float) -> str:
    if action > 0.05:
        return f"Charge battery at {action*50:.1f} kW"
    elif action < -0.05:
        return f"Discharge battery at {abs(action)*50:.1f} kW"
    return "Idle (no charge/discharge)"


# ── Routes ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "policy_loaded": _policy is not None}


@app.post("/act", response_model=ActionResponse)
async def act(req: StateRequest):
    from datetime import datetime, timezone
    obs = _build_obs(req)

    # Get raw action from policy or rule-based fallback
    if _policy is not None:
        raw_action, _ = _policy.predict(obs, deterministic=True)
        raw_action = float(raw_action[0])
    else:
        raw_action = _rule_based_action(req)

    # Apply safety gate
    prev_soc = _prev_soc.get(req.node_id)
    result   = apply_safety_gate(raw_action, req.battery_soc, req.voltage_pu, prev_soc)
    _prev_soc[req.node_id] = req.battery_soc

    response = ActionResponse(
        node_id         = req.node_id,
        raw_action      = raw_action,
        safe_action     = result.final_action,
        approved        = result.approved,
        violations      = result.violations,
        override_reason = result.override_reason,
        description     = _describe_action(result.final_action),
    )

    # Publish to Kafka
    payload = {
        "time":        datetime.now(timezone.utc).isoformat(),
        "node_id":     req.node_id,
        "action":      result.final_action,
        "approved":    result.approved,
        "violations":  result.violations,
        "soc":         req.battery_soc,
    }
    if _producer:
        _producer.produce("rl.actions", key=req.node_id, value=json.dumps(payload))
        _producer.poll(0)

    # Log to DB
    if _db_pool:
        try:
            async with _db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO control_log
                       (time, source, device_id, command_type, value, approved, safety_override, notes)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)""",
                    payload["time"], "rl_agent", req.node_id,
                    "charge" if result.final_action >= 0 else "discharge",
                    abs(result.final_action) * 50.0,
                    result.approved, not result.approved,
                    result.override_reason,
                )
        except Exception as exc:
            log.warning("DB log failed: %s", exc)

    return response


@app.post("/explain")
async def explain(req: StateRequest):
    """SHAP-based feature importance for the current action decision."""
    if _policy is None:
        raise HTTPException(503, "Policy not loaded")

    try:
        import shap
        obs = _build_obs(req)

        feature_names = ["soc", "load_norm", "solar_norm", "price_norm", "hour_sin", "hour_cos"]

        def predict_fn(X):
            actions = []
            for row in X:
                act, _ = _policy.predict(row.astype(np.float32), deterministic=True)
                actions.append(float(act[0]))
            return np.array(actions)

        # Background: perturb the observation slightly
        background = np.random.randn(50, len(obs)).astype(np.float32) * 0.1 + obs
        explainer  = shap.KernelExplainer(predict_fn, background)
        shap_vals  = explainer.shap_values(obs.reshape(1, -1), nsamples=100)

        explanation = {
            name: round(float(val), 6)
            for name, val in zip(feature_names, shap_vals[0])
        }
        return {
            "node_id":     req.node_id,
            "action":      predict_fn(obs.reshape(1, -1))[0],
            "shap_values": explanation,
        }
    except ImportError:
        return {"error": "shap not installed; run: pip install shap"}
    except Exception as exc:
        raise HTTPException(500, str(exc))


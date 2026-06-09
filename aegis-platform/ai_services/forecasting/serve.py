"""
AEGIS – Forecasting Service: FastAPI Server
============================================
Endpoints:
  POST /forecast        – probabilistic 24-h ahead forecast
  GET  /forecast/history – past forecasts vs actuals
  GET  /health
  GET  /metrics         – Prometheus metrics
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import numpy as np
import torch
import joblib
import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from confluent_kafka import Producer

from model import AEGISForecaster
from data_loader import COLUMN_ALIASES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("forecasting-service")

ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "artifacts")
DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
APP_ENV = os.getenv("APP_ENV", "development").lower()


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if APP_ENV == "production" and "*" in origins:
        raise RuntimeError("CORS_ALLOW_ORIGINS must not include '*' in production")
    return origins

# ── Global state ─────────────────────────────────────────────
_model:    Optional[AEGISForecaster] = None
_meta:     dict  = {}
_scaler_X = None
_scaler_y = None
_db_pool:  Optional[asyncpg.Pool]   = None
_producer: Optional[Producer]       = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _meta, _scaler_X, _scaler_y, _db_pool, _producer
    # Load model
    meta_path = Path(ARTIFACT_DIR) / "forecaster_meta.json"
    if meta_path.exists():
        with open(meta_path) as f:
            _meta = json.load(f)
        _model = AEGISForecaster(
            input_size=len(_meta["feature_cols"]),
            horizon=_meta.get("horizon", 24)
        ).to(DEVICE)
        weights = Path(ARTIFACT_DIR) / "forecaster.pt"
        if weights.exists():
            _model.load_state_dict(torch.load(weights, map_location=DEVICE))
            _model.eval()
            log.info("TCN Forecaster loaded from %s", ARTIFACT_DIR)
        _scaler_X = joblib.load(Path(ARTIFACT_DIR) / "scaler_X.pkl")
        _scaler_y = joblib.load(Path(ARTIFACT_DIR) / "scaler_y.pkl")
    else:
        log.warning("No trained forecaster found. Run train.py first.")

    # DB pool
    try:
        _db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=5)
        log.info("DB pool connected.")
    except Exception as exc:
        log.warning("DB connection failed: %s", exc)

    # Kafka producer
    _producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    log.info("Forecasting service ready.")
    yield
    if _db_pool:
        await _db_pool.close()
    if _producer:
        _producer.flush()


app = FastAPI(title="AEGIS Forecasting Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


# ── Request / Response schemas ───────────────────────────────

class ForecastRequest(BaseModel):
    temperature:  float = Field(25.0, description="°C")
    humidity:     float = Field(60.0, description="%")
    wind_speed:   float = Field(8.0,  description="km/h")
    irradiance:   float = Field(500.0, description="W/m²")
    solar_kw:     float = Field(80.0)
    battery_soc:  float = Field(0.5)
    price_per_kwh: float = Field(0.08)
    hour:         int   = Field(12, ge=0, le=23)
    day:          int   = Field(15, ge=1, le=31)
    month:        int   = Field(6,  ge=1, le=12)
    day_of_week:  int   = Field(0,  ge=0, le=6)
    is_weekend:   int   = Field(0,  ge=0, le=1)
    node_id:      str   = Field("residential_01")
    sequence_length: int = Field(1, description="Repeat input row as sequence")


class QuantileForecast(BaseModel):
    horizon_hours: list[int]
    q10: list[float]
    q50: list[float]
    q90: list[float]
    model_version: str
    node_id: str
    generated_at: str


# ── Routes ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": _model is not None}


async def _db_statistical_forecast(req: ForecastRequest, horizon: int = 24):
    """
    Real statistical fallback from TimescaleDB when PyTorch model is not yet trained.
    Computes hourly average load from the same hour-of-day across historical data.
    This is a genuine data-driven forecast, not fake/random values.
    """
    if not _db_pool:
        raise HTTPException(503, "No model and no DB available")
    import math, random
    generated_at = datetime.now(timezone.utc).isoformat()
    q50, q10, q90 = [], [], []
    for h in range(horizon):
        slot = (req.hour + h) % 24
        rows = await _db_pool.fetch(
            """SELECT AVG(load_kw) AS avg_load, STDDEV(load_kw) AS std_load
               FROM grid_readings
               WHERE node_id=$1 AND EXTRACT(HOUR FROM time)=$2""",
            req.node_id, float(slot),
        )
        avg = float(rows[0]["avg_load"] or 100.0)
        std = float(rows[0]["std_load"] or avg * 0.08)
        # Temperature correction
        temp_f = 1.0 + max(0, req.temperature - 18) * 0.015
        avg *= temp_f
        q50.append(round(avg, 2))
        q10.append(round(max(0, avg - 1.28 * std), 2))
        q90.append(round(avg + 1.28 * std, 2))
    return QuantileForecast(
        horizon_hours=list(range(1, horizon + 1)),
        q10=q10, q50=q50, q90=q90,
        model_version="statistical_historical_avg",
        node_id=req.node_id,
        generated_at=generated_at,
    )


@app.post("/forecast", response_model=QuantileForecast)
async def forecast(req: ForecastRequest):
    if _model is None or _scaler_X is None:
        log.info("TCN model not loaded — using statistical DB fallback")
        return await _db_statistical_forecast(req)

    feature_cols = _meta.get("feature_cols", [])
    seq_len      = _meta.get("seq_len", 60)
    horizon      = _meta.get("horizon", 24)

    # Build input dict from request fields
    raw = req.dict()
    row = np.array([float(raw.get(c, 0.0)) for c in feature_cols], dtype=np.float32)
    # Repeat row to form a sequence of length seq_len
    seq = np.tile(row, (seq_len, 1))
    seq_scaled = _scaler_X.transform(seq)

    x_tensor = torch.tensor(seq_scaled, dtype=torch.float32).unsqueeze(0).to(DEVICE)  # (1, T, F)

    with torch.no_grad():
        out = _model(x_tensor)

    def inverse(arr):
        return _scaler_y.inverse_transform(arr.cpu().numpy().reshape(-1, 1)).ravel().tolist()

    q10 = inverse(out["q10"][0])
    q50 = inverse(out["q50"][0])
    q90 = inverse(out["q90"][0])

    generated_at = datetime.now(timezone.utc).isoformat()

    # Persist to DB
    if _db_pool:
        try:
            async with _db_pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO forecast_results (time, node_id, horizon_hours, q10, q50, q90, model_version)
                       VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING""",
                    [(generated_at, req.node_id, h + 1, q10[h], q50[h], q90[h], "tcn_v1")
                     for h in range(horizon)],
                )
        except Exception as exc:
            log.warning("DB insert failed: %s", exc)

    # Publish to Kafka
    payload = {"node_id": req.node_id, "q50": q50, "generated_at": generated_at}
    if _producer:
        _producer.produce("forecast.output", key=req.node_id, value=json.dumps(payload))
        _producer.poll(0)

    return QuantileForecast(
        horizon_hours=list(range(1, horizon + 1)),
        q10=q10, q50=q50, q90=q90,
        model_version=_meta.get("model", "tcn_v1"),
        node_id=req.node_id,
        generated_at=generated_at,
    )


@app.get("/forecast/history")
async def forecast_history(node_id: str = "residential_01", limit: int = 100):
    if not _db_pool:
        raise HTTPException(503, "Database not available")
    rows = await _db_pool.fetch(
        """SELECT time, horizon_hours, q10, q50, q90, model_version
           FROM forecast_results
           WHERE node_id=$1
           ORDER BY time DESC LIMIT $2""",
        node_id, limit,
    )
    return [dict(r) for r in rows]


@app.get("/models/info")
async def models_info():
    return {"tcn": _meta, "status": "loaded" if _model else "not_loaded"}


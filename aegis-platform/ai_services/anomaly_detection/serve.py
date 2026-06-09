"""
AEGIS – Anomaly Detection Service: FastAPI Server
==================================================
• Trains/loads a GridVAE model on startup.
• Consumes `sensor.features` in a background task, scores each record.
• Publishes alerts to `anomaly.alerts` and stores in TimescaleDB.
• REST endpoints:
    GET  /anomalies          – recent alerts
    POST /score              – score a single record
    GET  /health
    GET  /metrics            – Prometheus
"""

import os
import json
import logging
import asyncio
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

import numpy as np
import torch
import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from confluent_kafka import Consumer, Producer, KafkaError
from sklearn.preprocessing import StandardScaler
import joblib

from vae_model import GridVAE, vae_loss
from causal_rules import AnomalyContext, Diagnosis, diagnose

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("anomaly-service")

ARTIFACT_DIR    = os.getenv("ARTIFACT_DIR", "artifacts")
DATA_DIR        = Path(os.getenv("AEGIS_DATA_DIR", Path(__file__).resolve().parents[2] / "data")).resolve()
DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
DEVICE          = torch.device("cuda" if torch.cuda.is_available() else "cpu")
APP_ENV         = os.getenv("APP_ENV", "development").lower()


def _cors_origins() -> list[str]:
    raw = os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    )
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if APP_ENV == "production" and "*" in origins:
        raise RuntimeError("CORS_ALLOW_ORIGINS must not include '*' in production")
    return origins

VAE_FEATURES = [
    "voltage_pu", "frequency_hz", "load_kw", "solar_kw",
    "battery_soc", "temperature", "humidity", "wind_speed",
]

_vae:      Optional[GridVAE] = None
_scaler:   Optional[StandardScaler] = None
_db_pool:  Optional[asyncpg.Pool] = None
_producer: Optional[Producer] = None
_recent_alerts: list = []   # in-memory ring buffer (last 200 alerts)


def _train_vae_on_normal_data():
    """Quick offline training from parquet if available."""
    global _vae, _scaler
    _vae    = GridVAE(input_dim=len(VAE_FEATURES)).to(DEVICE)
    _scaler = StandardScaler()

    parquet = DATA_DIR / "processed" / "microgrid_2024.parquet"
    if not parquet.exists():
        log.warning("No parquet found; VAE will use random weights.")
        _vae.threshold = 1.0
        return

    import pandas as pd
    df = pd.read_parquet(parquet)[VAE_FEATURES].dropna()
    # Use only rows with normal voltage/frequency as training data
    df_normal = df[(df["voltage_pu"] > 0.93) & (df["voltage_pu"] < 1.07)
                   & (df["frequency_hz"] > 49.5) & (df["frequency_hz"] < 50.5)]

    X = _scaler.fit_transform(df_normal.values.astype(np.float32))
    X_t = torch.tensor(X, dtype=torch.float32).to(DEVICE)

    optimizer = torch.optim.Adam(_vae.parameters(), lr=1e-3)
    _vae.train()
    for epoch in range(20):
        perm  = torch.randperm(len(X_t))
        total = 0.0
        for i in range(0, len(X_t), 256):
            batch = X_t[perm[i : i + 256]]
            optimizer.zero_grad()
            x_hat, mu, lv = _vae(batch)
            loss = vae_loss(batch, x_hat, mu, lv)
            loss.backward()
            optimizer.step()
            total += loss.item()
        if (epoch + 1) % 5 == 0:
            log.info("VAE epoch %d | loss=%.4f", epoch + 1, total)

    _vae.eval()
    # Compute threshold = 99th percentile of training reconstruction errors
    with torch.no_grad():
        errors = _vae.reconstruction_error(X_t).cpu().numpy()
    _vae.threshold = float(np.percentile(errors, 99))
    log.info("VAE threshold set to %.6f", _vae.threshold)

    torch.save(_vae.state_dict(), Path(ARTIFACT_DIR) / "vae.pt")
    joblib.dump(_scaler, Path(ARTIFACT_DIR) / "vae_scaler.pkl")
    log.info("VAE trained and saved.")


def _load_or_train_vae():
    global _vae, _scaler
    vae_path    = Path(ARTIFACT_DIR) / "vae.pt"
    scaler_path = Path(ARTIFACT_DIR) / "vae_scaler.pkl"
    if vae_path.exists() and scaler_path.exists():
        _vae    = GridVAE(input_dim=len(VAE_FEATURES)).to(DEVICE)
        _scaler = joblib.load(scaler_path)
        _vae.load_state_dict(torch.load(vae_path, map_location=DEVICE))
        _vae.eval()
        log.info("VAE loaded from %s", ARTIFACT_DIR)
        # Load threshold
        import json as _json
        thr_path = Path(ARTIFACT_DIR) / "vae_threshold.json"
        if thr_path.exists():
            with open(thr_path) as f:
                _vae.threshold = _json.load(f)["threshold"]
    else:
        log.info("Training VAE from scratch ...")
        Path(ARTIFACT_DIR).mkdir(parents=True, exist_ok=True)
        _train_vae_on_normal_data()


def _kafka_consumer_thread():
    """Background thread: consume sensor.features → score → publish alerts."""
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id":          "anomaly-detector",
        "auto.offset.reset": "latest",
    })
    consumer.subscribe(["sensor.features"])

    recent_alert_times: list[float] = []

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("Kafka: %s", msg.error())
                continue

            try:
                record   = json.loads(msg.value())
                features = np.array(
                    [float(record.get(f, 0.0) or 0.0) for f in VAE_FEATURES],
                    dtype=np.float32
                )

                if _vae is None or _scaler is None:
                    continue

                scaled = _scaler.transform(features.reshape(1, -1))
                x_t    = torch.tensor(scaled, dtype=torch.float32).to(DEVICE)
                error  = float(_vae.reconstruction_error(x_t).cpu().item())
                is_anom = error > _vae.threshold

                if is_anom:
                    import time
                    now = time.time()
                    recent_alert_times = [t for t in recent_alert_times if now - t < 300]
                    recent_alerts_count = len(recent_alert_times)
                    recent_alert_times.append(now)

                    ctx = AnomalyContext(
                        node_id              = record.get("node_id", "unknown"),
                        reconstruction_error = error,
                        voltage_pu           = float(record.get("voltage_pu", 1.0)),
                        frequency_hz         = float(record.get("frequency_hz", 50.0)),
                        load_kw              = float(record.get("load_kw", 0.0)),
                        solar_kw             = float(record.get("solar_kw", 0.0)),
                        battery_soc          = float(record.get("battery_soc", 0.5)),
                        temperature          = float(record.get("temperature", 25.0)),
                        load_mean_15m        = float(record.get("load_kw_mean_15m", 0.0)),
                        load_std_15m         = float(record.get("load_kw_std_15m", 0.0)),
                        recent_alerts        = recent_alerts_count,
                    )
                    diag = diagnose(ctx)

                    alert = {
                        "time":     datetime.now(timezone.utc).isoformat(),
                        "node_id":  ctx.node_id,
                        "severity": diag.severity,
                        "reconstruction_error": error,
                        "diagnosis_code":  diag.code,
                        "diagnosis":       diag.description,
                        "recommended_action": diag.recommended_action,
                        "confidence":      diag.confidence,
                    }
                    _recent_alerts.append(alert)
                    if len(_recent_alerts) > 200:
                        _recent_alerts.pop(0)

                    if _producer:
                        _producer.produce(
                            "anomaly.alerts",
                            key=ctx.node_id,
                            value=json.dumps(alert),
                        )
                        _producer.poll(0)

                    log.warning("ANOMALY [%s] node=%s err=%.4f diag=%s",
                                diag.severity, ctx.node_id, error, diag.code)

            except Exception as exc:
                log.exception("Scoring error: %s", exc)
    finally:
        consumer.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool, _producer
    _load_or_train_vae()

    try:
        _db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=5)
    except Exception as exc:
        log.warning("DB unavailable: %s", exc)

    _producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})

    t = threading.Thread(target=_kafka_consumer_thread, daemon=True)
    t.start()
    log.info("Anomaly detection service ready.")
    yield
    if _db_pool:
        await _db_pool.close()
    if _producer:
        _producer.flush()


app = FastAPI(title="AEGIS Anomaly Detection", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


class ScoreRequest(BaseModel):
    voltage_pu:   float = 1.0
    frequency_hz: float = 50.0
    load_kw:      float = 200.0
    solar_kw:     float = 50.0
    battery_soc:  float = 0.5
    temperature:  float = 25.0
    humidity:     float = 60.0
    wind_speed:   float = 8.0
    node_id:      str   = "residential_01"


@app.get("/health")
async def health():
    return {"status": "ok", "vae_loaded": _vae is not None,
            "threshold": _vae.threshold if _vae else None}


@app.post("/score")
async def score(req: ScoreRequest):
    if _vae is None or _scaler is None:
        raise HTTPException(503, "VAE not loaded")
    features = np.array([getattr(req, f) for f in VAE_FEATURES], dtype=np.float32)
    scaled   = _scaler.transform(features.reshape(1, -1))
    x_t      = torch.tensor(scaled, dtype=torch.float32).to(DEVICE)
    error    = float(_vae.reconstruction_error(x_t).cpu().item())
    is_anom  = error > _vae.threshold
    diag     = None
    if is_anom:
        ctx  = AnomalyContext(node_id=req.node_id, reconstruction_error=error,
                              **{f: getattr(req, f) for f in VAE_FEATURES
                                 if hasattr(req, f) and f != "node_id"})
        d    = diagnose(ctx)
        diag = {"severity": d.severity, "code": d.code, "description": d.description,
                "recommended_action": d.recommended_action, "confidence": d.confidence}
    return {"node_id": req.node_id, "reconstruction_error": error,
            "threshold": _vae.threshold, "is_anomaly": is_anom, "diagnosis": diag}


@app.get("/anomalies")
async def get_anomalies(limit: int = 50):
    return _recent_alerts[-limit:]


@app.get("/anomalies/db")
async def get_anomalies_db(limit: int = 100):
    if not _db_pool:
        raise HTTPException(503, "Database not available")
    rows = await _db_pool.fetch(
        "SELECT * FROM anomaly_alerts ORDER BY time DESC LIMIT $1", limit
    )
    return [dict(r) for r in rows]


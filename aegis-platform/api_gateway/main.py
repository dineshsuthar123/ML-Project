"""
AEGIS – API Gateway
=====================
Unified FastAPI backend aggregating all microservices.
Provides:
  REST:
    GET  /api/latest-telemetry
    GET  /api/forecast
    POST /api/forecast
    GET  /api/anomalies
    GET  /api/control/status
    POST /api/control/manual
    POST /api/demand-response
    GET  /api/system/health
  WebSocket:
    /ws/live-telemetry  – streams sensor data + predictions in real time
  Auth:
    POST /auth/token    – JWT login
"""

import os
import logging
from contextlib import asynccontextmanager

import asyncpg
import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from websocket_manager import WebSocketManager, kafka_broadcast_task, db_poll_broadcast_task
from routes.forecast  import router as forecast_router
from routes.anomaly   import router as anomaly_router
from routes.control   import router as control_router
from routes.dashboard import router as dashboard_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("api-gateway")

DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)
REDIS_URL       = f"redis://{os.getenv('REDIS_HOST','redis')}:{os.getenv('REDIS_PORT','6379')}"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
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

ws_manager = WebSocketManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    # DB pool
    try:
        app.state.db = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=10)
        log.info("DB pool ready.")
    except Exception as exc:
        log.warning("DB unavailable: %s", exc)
        app.state.db = None

    # Redis
    try:
        app.state.redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        await app.state.redis.ping()
        log.info("Redis connected.")
    except Exception as exc:
        log.warning("Redis unavailable: %s", exc)
        app.state.redis = None

    # Start Kafka → WebSocket broadcast
    app.state.ws_manager = ws_manager
    task = asyncio.create_task(
        kafka_broadcast_task(KAFKA_BOOTSTRAP, ws_manager)
    )
    # Start DB polling fallback (always has data even without Kafka)
    db_task = asyncio.create_task(
        db_poll_broadcast_task(app.state.db, ws_manager)
    )
    log.info("API Gateway ready.")
    yield
    task.cancel()
    db_task.cancel()
    if app.state.db:
        await app.state.db.close()
    if app.state.redis:
        await app.state.redis.aclose()


app = FastAPI(
    title="AEGIS API Gateway",
    description="Autonomous Energy Grid Intelligent System – Unified API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Instrumentator().instrument(app).expose(app)

app.include_router(forecast_router,  prefix="/api")
app.include_router(anomaly_router,   prefix="/api")
app.include_router(control_router,   prefix="/api")
app.include_router(dashboard_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "aegis-api-gateway"}


@app.get("/api/system/health")
async def system_health():
    return {
        "gateway": "ok",
        "services": {
            "forecasting":      os.getenv("FORECASTING_SERVICE_URL"),
            "anomaly":          os.getenv("ANOMALY_SERVICE_URL"),
            "rl_agent":         os.getenv("RL_AGENT_SERVICE_URL"),
            "demand_response":  os.getenv("DR_SERVICE_URL"),
        },
    }


# WebSocket endpoint
from fastapi import WebSocket
from websocket_manager import WebSocketManager

@app.websocket("/ws/live-telemetry")
async def ws_live(websocket: WebSocket):
    await app.state.ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; broadcast happens from Kafka task
            await websocket.receive_text()
    except Exception:
        app.state.ws_manager.disconnect(websocket)


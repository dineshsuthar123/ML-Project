"""
AEGIS – Demand Response Service: FastAPI Server
================================================
POST /demand_response  – run DR optimization
GET  /demand_response/history
GET  /health
GET  /metrics
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from prometheus_fastapi_instrumentator import Instrumentator

from optimizer import DRParticipant, optimize_demand_response, DRResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("demand-response-service")

DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)
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

_db_pool: Optional[asyncpg.Pool] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _db_pool
    try:
        _db_pool = await asyncpg.create_pool(DB_DSN, min_size=1, max_size=3)
    except Exception as exc:
        log.warning("DB unavailable: %s", exc)
    log.info("Demand Response service ready.")
    yield
    if _db_pool:
        await _db_pool.close()


app = FastAPI(title="AEGIS Demand Response", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"])
Instrumentator().instrument(app).expose(app)


# ── Schemas ──────────────────────────────────────────────────

class ParticipantIn(BaseModel):
    participant_id:     str
    max_curtailment_kw: float = Field(..., gt=0)
    min_curtailment_kw: float = Field(0.0, ge=0)
    comfort_penalty:    float = Field(1.0, gt=0)
    baseline_load_kw:   float = Field(0.0, ge=0)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_curtailment_kw > self.max_curtailment_kw:
            raise ValueError("min_curtailment_kw must be <= max_curtailment_kw")
        return self


class DRRequest(BaseModel):
    required_total_kw: float = Field(..., gt=0, description="Total curtailment needed (kW)")
    participants:      list[ParticipantIn]
    event_id:          str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ScheduleOut(BaseModel):
    participant_id:           str
    allocated_curtailment_kw: float
    accepted:                 bool
    comfort_cost:             float


class DRResponseOut(BaseModel):
    event_id:            str
    total_allocated_kw:  float
    total_required_kw:   float
    schedules:           list[ScheduleOut]
    total_comfort_cost:  float
    feasible:            bool
    status_message:      str
    generated_at:        str


# ── Routes ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/demand_response", response_model=DRResponseOut)
async def demand_response(req: DRRequest):
    participants = [
        DRParticipant(
            participant_id     = p.participant_id,
            max_curtailment_kw = p.max_curtailment_kw,
            min_curtailment_kw = p.min_curtailment_kw,
            comfort_penalty    = p.comfort_penalty,
            baseline_load_kw   = p.baseline_load_kw,
        )
        for p in req.participants
    ]

    result: DRResult = optimize_demand_response(participants, req.required_total_kw)
    generated_at = datetime.now(timezone.utc).isoformat()

    # Persist schedules
    if _db_pool:
        try:
            async with _db_pool.acquire() as conn:
                await conn.executemany(
                    """INSERT INTO dr_schedules
                       (time, participant_id, required_curtailment_kw, allocated_kw, accepted)
                       VALUES ($1,$2,$3,$4,$5)""",
                    [
                        (generated_at, s.participant_id,
                         req.required_total_kw, s.allocated_curtailment_kw, s.accepted)
                        for s in result.schedules
                    ],
                )
        except Exception as exc:
            log.warning("DB insert failed: %s", exc)

    return DRResponseOut(
        event_id           = req.event_id,
        total_allocated_kw = result.total_allocated_kw,
        total_required_kw  = result.total_required_kw,
        schedules          = [ScheduleOut(**s.__dict__) for s in result.schedules],
        total_comfort_cost = result.total_comfort_cost,
        feasible           = result.feasible,
        status_message     = result.status_message,
        generated_at       = generated_at,
    )


@app.get("/demand_response/history")
async def dr_history(limit: int = 50):
    if not _db_pool:
        raise HTTPException(503, "Database not available")
    rows = await _db_pool.fetch(
        "SELECT * FROM dr_schedules ORDER BY time DESC LIMIT $1", limit
    )
    return [dict(r) for r in rows]


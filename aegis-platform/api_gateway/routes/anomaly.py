"""AEGIS – Anomaly Routes (API Gateway)"""

import os
from fastapi import APIRouter
from pydantic import BaseModel
from routes.upstream import request_json

router = APIRouter(tags=["Anomaly Detection"])
ANOMALY_URL = os.getenv("ANOMALY_SERVICE_URL", "http://anomaly:8002")


class ScoreIn(BaseModel):
    voltage_pu:   float = 1.0
    frequency_hz: float = 50.0
    load_kw:      float = 200.0
    solar_kw:     float = 50.0
    battery_soc:  float = 0.5
    temperature:  float = 25.0
    humidity:     float = 60.0
    wind_speed:   float = 8.0
    node_id:      str   = "residential_01"


@router.get("/anomalies")
async def get_anomalies(limit: int = 50):
    return await request_json("GET", f"{ANOMALY_URL}/anomalies", timeout=10, params={"limit": limit})


@router.post("/anomalies/score")
async def score(body: ScoreIn):
    return await request_json("POST", f"{ANOMALY_URL}/score", timeout=10, json=body.model_dump())


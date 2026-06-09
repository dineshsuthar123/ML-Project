"""AEGIS – Anomaly Routes (API Gateway)"""

import os
import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{ANOMALY_URL}/anomalies", params={"limit": limit})
    return r.json()


@router.post("/anomalies/score")
async def score(body: ScoreIn):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(f"{ANOMALY_URL}/score", json=body.dict())
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()


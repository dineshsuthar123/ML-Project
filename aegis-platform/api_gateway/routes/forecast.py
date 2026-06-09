"""AEGIS – Forecast Routes (API Gateway)"""

import os
import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter(tags=["Forecasting"])
FORECAST_URL = os.getenv("FORECASTING_SERVICE_URL", "http://forecasting:8001")


class ForecastIn(BaseModel):
    temperature:   float = 25.0
    humidity:      float = 60.0
    wind_speed:    float = 8.0
    irradiance:    float = 500.0
    solar_kw:      float = 80.0
    battery_soc:   float = 0.5
    price_per_kwh: float = 0.08
    hour:          int   = 12
    day:           int   = 15
    month:         int   = 6
    day_of_week:   int   = 0
    is_weekend:    int   = 0
    node_id:       str   = "residential_01"


@router.get("/forecast/history")
async def forecast_history(node_id: str = "residential_01", limit: int = 100):
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{FORECAST_URL}/forecast/history",
                             params={"node_id": node_id, "limit": limit})
    return r.json()


@router.post("/forecast")
async def forecast(body: ForecastIn):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{FORECAST_URL}/forecast", json=body.dict())
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()


@router.get("/forecast/models")
async def forecast_models():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{FORECAST_URL}/models/info")
    return r.json()


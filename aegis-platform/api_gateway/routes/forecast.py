"""AEGIS – Forecast Routes (API Gateway)"""

import os
from fastapi import APIRouter
from pydantic import BaseModel
from routes.upstream import request_json

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
    return await request_json(
        "GET", f"{FORECAST_URL}/forecast/history", timeout=10,
        params={"node_id": node_id, "limit": limit},
    )


@router.post("/forecast")
async def forecast(body: ForecastIn):
    return await request_json(
        "POST", f"{FORECAST_URL}/forecast", timeout=30, json=body.model_dump()
    )


@router.get("/forecast/models")
async def forecast_models():
    return await request_json("GET", f"{FORECAST_URL}/models/info", timeout=10)


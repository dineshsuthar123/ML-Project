"""AEGIS – Control Routes (API Gateway) with JWT auth"""

import os
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
import asyncpg
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from jose import JWTError, jwt
from passlib.context import CryptContext

log = logging.getLogger("control-routes")
router = APIRouter(tags=["Control"])

RL_URL = os.getenv("RL_AGENT_SERVICE_URL", "http://rl-agent:8003")
DR_URL = os.getenv("DR_SERVICE_URL",       "http://demand-response:8004")

APP_ENV       = os.getenv("APP_ENV", "development").lower()
DEMO_JWT_SECRET = "supersecret_aegis_jwt_2026"
JWT_SECRET    = os.getenv("JWT_SECRET", DEMO_JWT_SECRET)
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE    = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2      = OAuth2PasswordBearer(tokenUrl="/api/control/token")

if APP_ENV == "production" and JWT_SECRET == DEMO_JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set to a non-demo value in production")


# ── Auth helpers ─────────────────────────────────────────────

def create_token(data: dict) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE)
    return jwt.encode({**data, "exp": expire}, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(token: str = Depends(oauth2)):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user = payload.get("sub")
        if not user:
            raise HTTPException(401, "Invalid token")
        return user
    except JWTError:
        raise HTTPException(401, "Invalid token")


def _demo_auth_enabled() -> bool:
    return os.getenv("AEGIS_ALLOW_DEMO_AUTH", "false").lower() in {"1", "true", "yes"}


async def _authenticate_user(db: Optional[asyncpg.Pool], username: str, password: str) -> Optional[dict]:
    if not db:
        return None
    row = await db.fetchrow(
        "SELECT username, password_hash, role FROM users WHERE username=$1",
        username,
    )
    if not row or not pwd_context.verify(password, row["password_hash"]):
        return None
    return {"username": row["username"], "role": row["role"]}


# ── Routes ───────────────────────────────────────────────────

@router.post("/control/token")
async def login(request: Request, form: OAuth2PasswordRequestForm = Depends()):
    db: Optional[asyncpg.Pool] = getattr(request.app.state, "db", None)
    user = await _authenticate_user(db, form.username, form.password)

    if user:
        token = create_token({"sub": user["username"], "role": user["role"]})
        return {"access_token": token, "token_type": "bearer"}

    if _demo_auth_enabled() and form.username == "admin" and form.password == "admin123":
        token = create_token({"sub": form.username, "role": "admin"})
        return {"access_token": token, "token_type": "bearer"}

    raise HTTPException(401, "Invalid credentials")


class ActionRequest(BaseModel):
    battery_soc:   float = 0.5
    load_kw:       float = 200.0
    solar_kw:      float = 50.0
    price_per_kwh: float = 0.08
    voltage_pu:    float = 1.0
    hour:          int   = 12
    node_id:       str   = "commercial_01"


@router.post("/control/rl-action")
async def rl_action(body: ActionRequest, user: str = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{RL_URL}/act", json=body.dict())
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()


@router.post("/control/explain")
async def explain(body: ActionRequest, user: str = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{RL_URL}/explain", json=body.dict())
    return r.json()


class ManualCommandIn(BaseModel):
    device_id:    str
    command_type: str   # charge | discharge | curtail | shed_load
    value_kw:     float
    notes:        str = ""


@router.post("/control/manual")
async def manual_command(
    body: ManualCommandIn,
    request: Request,
    user: str = Depends(get_current_user),
):
    """Operator manual override."""
    db: asyncpg.Pool = request.app.state.db
    now = datetime.now(timezone.utc).isoformat()
    if db:
        await db.execute(
            """INSERT INTO control_log
               (time, source, device_id, command_type, value, approved, safety_override, notes)
               VALUES ($1,'operator',$2,$3,$4,TRUE,FALSE,$5)""",
            now, body.device_id, body.command_type, body.value_kw,
            f"Manual by {user}: {body.notes}",
        )
    log.info("Manual command by %s: %s %s @ %.1f kW", user, body.device_id, body.command_type, body.value_kw)
    return {"status": "dispatched", "command": body.dict(), "operator": user, "time": now}


@router.get("/control/status")
async def control_status(request: Request):
    db: asyncpg.Pool = request.app.state.db
    if not db:
        return {"error": "DB unavailable"}
    rows = await db.fetch(
        "SELECT * FROM control_log ORDER BY time DESC LIMIT 20"
    )
    return [dict(r) for r in rows]


class DRIn(BaseModel):
    required_total_kw: float
    participants: list[dict]


@router.post("/demand-response")
async def demand_response(body: DRIn, user: str = Depends(get_current_user)):
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(f"{DR_URL}/demand_response", json=body.dict())
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()


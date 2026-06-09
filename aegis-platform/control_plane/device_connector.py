"""
AEGIS – Device Connector (Simulated)
======================================
In a real system this would communicate via MQTT or OPC-UA.
For demo purposes, commands are:
  1. Printed to console (human-readable log)
  2. Stored in TimescaleDB `control_log` table via synchronous asyncpg wrapper
  3. Cached in Redis for the API gateway to read

This module simulates the "last mile" of device communication.
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timezone

log = logging.getLogger("device-connector")

DB_DSN = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

_redis = None


def _get_redis():
    global _redis
    if _redis is None:
        try:
            import redis as _r
            _redis = _r.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            _redis.ping()
        except Exception as exc:
            log.warning("Redis unavailable: %s", exc)
            _redis = None
    return _redis


class DeviceConnector:
    """
    Simulated device connector.
    Logs all commands and caches latest device state in Redis.
    """

    def send_command(
        self,
        device_id:    str,
        command_type: str,
        value_kw:     float,
        source:       str = "rule_engine",
        notes:        str = "",
    ):
        """
        Send a control command to a simulated device.

        Parameters
        ----------
        device_id    : node identifier (e.g. 'commercial_01')
        command_type : 'charge' | 'discharge' | 'curtail' | 'shed_load'
        value_kw     : power setpoint in kW
        source       : originating service
        notes        : human-readable context
        """
        now = datetime.now(timezone.utc).isoformat()
        log.info(
            "[DEVICE CMD] %s → %s  %s @ %.1f kW  (%s)",
            source, device_id, command_type.upper(), value_kw, now
        )

        payload = {
            "time":         now,
            "device_id":    device_id,
            "command_type": command_type,
            "value_kw":     value_kw,
            "source":       source,
            "notes":        notes,
        }

        # Cache latest state in Redis (TTL = 5 min)
        r = _get_redis()
        if r:
            try:
                r.setex(f"device:{device_id}:last_cmd", 300, json.dumps(payload))
                r.lpush("device:command_log", json.dumps(payload))
                r.ltrim("device:command_log", 0, 999)   # keep last 1000 commands
            except Exception as exc:
                log.warning("Redis write failed: %s", exc)

        # Async DB insert via run_in_executor
        asyncio.get_event_loop().run_until_complete(self._db_insert(payload))

    async def _db_insert(self, payload: dict):
        try:
            import asyncpg
            conn = await asyncpg.connect(DB_DSN)
            await conn.execute(
                """INSERT INTO control_log
                   (time, source, device_id, command_type, value, approved, notes)
                   VALUES ($1,$2,$3,$4,$5,TRUE,$6)""",
                payload["time"], payload["source"], payload["device_id"],
                payload["command_type"], payload["value_kw"], payload["notes"],
            )
            await conn.close()
        except Exception as exc:
            log.warning("DB log failed: %s", exc)


"""
AEGIS – WebSocket Manager + Kafka Broadcast + DB Polling Fallback
"""

import json
import asyncio
import logging
from typing import Set

from fastapi import WebSocket
from aiokafka import AIOKafkaConsumer

log = logging.getLogger("ws-manager")

TOPICS = ["sensor.features", "forecast.output", "anomaly.alerts", "rl.actions"]


class WebSocketManager:
    def __init__(self):
        self._clients: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        log.info("WS client connected. Total: %d", len(self._clients))

    def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        log.info("WS client disconnected. Total: %d", len(self._clients))

    async def broadcast(self, message: str):
        dead = set()
        for ws in list(self._clients):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)


async def kafka_broadcast_task(bootstrap_servers: str, manager: WebSocketManager):
    """Consume Kafka topics and broadcast to WebSocket clients."""
    while True:
        try:
            consumer = AIOKafkaConsumer(
                *TOPICS,
                bootstrap_servers=bootstrap_servers,
                group_id="ws-broadcaster",
                auto_offset_reset="latest",
                value_deserializer=lambda v: v.decode("utf-8"),
            )
            await consumer.start()
            log.info("Kafka → WS broadcaster started on topics: %s", TOPICS)
            try:
                async for msg in consumer:
                    if not manager._clients:
                        continue
                    try:
                        envelope = json.dumps({
                            "topic":   msg.topic,
                            "key":     msg.key.decode() if msg.key else None,
                            "payload": json.loads(msg.value),
                            "offset":  msg.offset,
                        })
                        await manager.broadcast(envelope)
                    except Exception as exc:
                        log.debug("Broadcast error: %s", exc)
            finally:
                await consumer.stop()
        except Exception as exc:
            log.warning("Kafka consumer error: %s — retrying in 5s", exc)
            await asyncio.sleep(5)


async def db_poll_broadcast_task(db_pool, manager: WebSocketManager):
    """
    Fallback: every 3 seconds query TimescaleDB for the latest telemetry
    and broadcast as sensor.features messages so the frontend always has live data.
    """
    while True:
        await asyncio.sleep(3)
        if not manager._clients or not db_pool:
            continue
        try:
            rows = await db_pool.fetch(
                """SELECT DISTINCT ON (node_id)
                       node_id, time, load_kw, solar_kw, battery_soc,
                       voltage_pu, frequency_hz, temperature, humidity,
                       wind_speed, irradiance, price_per_kwh
                   FROM grid_readings
                   ORDER BY node_id, time DESC"""
            )
            for row in rows:
                payload = dict(row)
                # make time JSON-serialisable
                if payload.get("time"):
                    payload["time"] = str(payload["time"])
                envelope = json.dumps({
                    "topic":   "sensor.features",
                    "key":     payload.get("node_id"),
                    "payload": payload,
                    "offset":  -1,
                })
                await manager.broadcast(envelope)
        except Exception as exc:
            log.debug("DB poll error: %s", exc)


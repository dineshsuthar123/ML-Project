"""
AEGIS – Control Plane: Rule Engine / State Machine
====================================================
Consumes from `rl.actions` and `anomaly.alerts`.
Implements a safety state machine:

  States: NORMAL → PEAK_PRICING → EMERGENCY → ISLANDED

Transitions and allowed actions per state:
  NORMAL        : all actions allowed
  PEAK_PRICING  : discharge allowed, charge restricted
  EMERGENCY     : only load shedding / curtailment allowed; no new dispatch
  ISLANDED      : local generation only; no grid interaction

Forwards approved commands to device_connector.
"""

import os
import json
import logging
import threading
from datetime import datetime, timezone
from enum import Enum

from confluent_kafka import Consumer, Producer, KafkaError
from device_connector import DeviceConnector

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("rule-engine")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")


class GridState(str, Enum):
    NORMAL       = "NORMAL"
    PEAK_PRICING = "PEAK_PRICING"
    EMERGENCY    = "EMERGENCY"
    ISLANDED     = "ISLANDED"


TRANSITION_RULES = {
    # (from_state, trigger) → to_state
    (GridState.NORMAL,       "HIGH_PRICE"):      GridState.PEAK_PRICING,
    (GridState.NORMAL,       "CRITICAL_ANOMALY"): GridState.EMERGENCY,
    (GridState.PEAK_PRICING, "NORMAL_PRICE"):    GridState.NORMAL,
    (GridState.PEAK_PRICING, "CRITICAL_ANOMALY"): GridState.EMERGENCY,
    (GridState.EMERGENCY,    "ISLANDED"):         GridState.ISLANDED,
    (GridState.EMERGENCY,    "RESTORED"):         GridState.NORMAL,
    (GridState.ISLANDED,     "RESTORED"):         GridState.NORMAL,
}

ALLOWED_ACTIONS = {
    GridState.NORMAL:       {"charge", "discharge", "curtail", "shed_load"},
    GridState.PEAK_PRICING: {"discharge", "shed_load"},
    GridState.EMERGENCY:    {"shed_load"},
    GridState.ISLANDED:     {"shed_load"},
}


class RuleEngine:
    def __init__(self):
        self.state     = GridState.NORMAL
        self.connector = DeviceConnector()
        self._lock     = threading.Lock()

    def transition(self, trigger: str):
        key = (self.state, trigger)
        if key in TRANSITION_RULES:
            new_state = TRANSITION_RULES[key]
            log.info("State transition: %s → %s  (trigger=%s)", self.state, new_state, trigger)
            self.state = new_state

    def process_rl_action(self, msg: dict):
        node_id = msg.get("node_id", "unknown")
        action  = msg.get("action", 0.0)
        approved = msg.get("approved", True)

        if not approved:
            log.info("Action for %s rejected by safety gate – skipping.", node_id)
            return

        command_type = "charge" if action >= 0 else "discharge"

        with self._lock:
            if command_type not in ALLOWED_ACTIONS[self.state]:
                log.info(
                    "Action '%s' not allowed in state %s for node %s",
                    command_type, self.state, node_id
                )
                return
            self.connector.send_command(node_id, command_type, abs(action) * 50.0)

    def process_anomaly_alert(self, alert: dict):
        severity = alert.get("severity", "LOW")
        if severity == "CRITICAL":
            self.transition("CRITICAL_ANOMALY")
        # Price trigger (check price field if included in alert context)
        price = alert.get("price_per_kwh", 0.0)
        if price and float(price) > 0.10:
            self.transition("HIGH_PRICE")
        elif price and float(price) <= 0.05:
            self.transition("NORMAL_PRICE")

    def run(self):
        consumer = Consumer({
            "bootstrap.servers": KAFKA_BOOTSTRAP,
            "group.id":          "rule-engine",
            "auto.offset.reset": "latest",
        })
        consumer.subscribe(["rl.actions", "anomaly.alerts"])
        log.info("Rule engine started. State: %s", self.state)

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
                    data = json.loads(msg.value())
                    if msg.topic() == "rl.actions":
                        self.process_rl_action(data)
                    elif msg.topic() == "anomaly.alerts":
                        self.process_anomaly_alert(data)
                except Exception as exc:
                    log.exception("Rule engine processing error: %s", exc)
        finally:
            consumer.close()


if __name__ == "__main__":
    RuleEngine().run()


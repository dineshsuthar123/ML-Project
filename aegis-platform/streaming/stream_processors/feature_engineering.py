"""
AEGIS – Stream Feature Engineering Processor
=============================================
Consumes `sensor.raw`, computes rolling-window statistics
(5-min, 15-min, 1-hr mean/std), and produces enriched records
to `sensor.features`.

Uses plain confluent_kafka (no Faust dependency) with an
in-memory deque per node to maintain windows.
"""

import os
import json
import logging
from collections import defaultdict, deque
from datetime import datetime

from confluent_kafka import Consumer, Producer, KafkaError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("feature-engineering")

KAFKA_BOOTSTRAP  = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
INPUT_TOPIC      = "sensor.raw"
OUTPUT_TOPIC     = "sensor.features"
GROUP_ID         = "feature-engineering-group"

NUMERIC_COLS = ["load_kw", "solar_kw", "temperature", "humidity",
                "wind_speed", "irradiance", "voltage_pu", "frequency_hz"]

# Window sizes in number of 1-minute samples
WINDOWS = {"5m": 5, "15m": 15, "1h": 60}


def delivery_report(err, msg):
    if err:
        log.error("Delivery failed: %s", err)


class WindowAggregator:
    """Maintains rolling windows per (node_id, column)."""

    def __init__(self):
        self.buffers: dict[str, dict[str, deque]] = defaultdict(
            lambda: {col: deque(maxlen=WINDOWS["1h"]) for col in NUMERIC_COLS}
        )

    def update(self, node_id: str, record: dict) -> dict:
        buf = self.buffers[node_id]
        for col in NUMERIC_COLS:
            val = record.get(col)
            if val is not None:
                buf[col].append(float(val))

        features = dict(record)
        for col in NUMERIC_COLS:
            values = list(buf[col])
            for name, size in WINDOWS.items():
                window = values[-size:] if len(values) >= size else values
                if window:
                    import statistics
                    features[f"{col}_mean_{name}"] = round(sum(window) / len(window), 4)
                    features[f"{col}_std_{name}"]  = round(statistics.pstdev(window), 4)
                else:
                    features[f"{col}_mean_{name}"] = None
                    features[f"{col}_std_{name}"]  = None

        # Hour and day-of-week features
        try:
            t = datetime.fromisoformat(record.get("time", ""))
            features["hour"]       = t.hour
            features["day_of_week"] = t.weekday()
            features["month"]      = t.month
            features["is_weekend"] = int(t.weekday() >= 5)
        except Exception:
            pass

        return features


def main():
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id":          GROUP_ID,
        "auto.offset.reset": "earliest",
    })
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    consumer.subscribe([INPUT_TOPIC])

    aggregator = WindowAggregator()
    log.info("Feature engineering processor started. Consuming '%s' → '%s'", INPUT_TOPIC, OUTPUT_TOPIC)

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                log.error("Kafka error: %s", msg.error())
                continue

            try:
                record   = json.loads(msg.value())
                node_id  = record.get("node_id", "unknown")
                enriched = aggregator.update(node_id, record)
                producer.produce(
                    OUTPUT_TOPIC,
                    key=node_id,
                    value=json.dumps(enriched),
                    callback=delivery_report,
                )
                producer.poll(0)
            except Exception as exc:
                log.exception("Processing error: %s", exc)
    finally:
        consumer.close()
        producer.flush()


if __name__ == "__main__":
    main()


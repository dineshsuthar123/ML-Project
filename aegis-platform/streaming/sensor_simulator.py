"""
AEGIS – Sensor Simulator
=========================
Reads the digital-twin Parquet file and publishes each row as a JSON
message to the Kafka topic `sensor.raw` at an accelerated simulation
rate (default: 1 msg/s = 1 simulated minute).
"""

import os
import json
import time
import logging
from datetime import datetime

import pandas as pd
from confluent_kafka import Producer

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sensor-simulator")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC           = "sensor.raw"
PARQUET_PATH    = os.path.join(os.path.dirname(__file__), "data", "processed", "microgrid_2024.parquet")
SPEED_FACTOR    = int(os.getenv("SIMULATION_SPEED_FACTOR", "60"))  # msgs/second


def delivery_report(err, msg):
    if err:
        log.error("Delivery failed: %s", err)


def main():
    log.info("Loading Parquet from %s ...", PARQUET_PATH)
    df = pd.read_parquet(PARQUET_PATH)
    df = df.sort_values("time").reset_index(drop=True)
    log.info("Loaded %d rows. Publishing to topic '%s' (looping forever) ...", len(df), TOPIC)

    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    interval = 1.0 / SPEED_FACTOR  # seconds between messages
    loop = 0

    while True:
        loop += 1
        log.info("Starting simulation loop #%d ...", loop)
        for _, row in df.iterrows():
            record = {k: (v.isoformat() if isinstance(v, datetime) else float(v) if hasattr(v, "item") else v)
                      for k, v in row.items()}
            record["published_at"] = datetime.utcnow().isoformat()

            producer.produce(
                TOPIC,
                key=record.get("node_id", "unknown"),
                value=json.dumps(record),
                callback=delivery_report,
            )
            producer.poll(0)
            time.sleep(interval)

        producer.flush()
        log.info("Loop #%d complete — restarting.", loop)


if __name__ == "__main__":
    main()


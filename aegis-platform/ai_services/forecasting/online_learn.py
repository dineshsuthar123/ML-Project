"""
AEGIS – Online Learning with River
====================================
Incrementally updates a linear regression (Hoeffding Tree fallback)
every time a new actual reading arrives from Kafka `sensor.features`.
Provides a continuous model that adapts to distribution drift.
"""

import os
import json
import logging
import pickle
from confluent_kafka import Consumer, KafkaError
from river import linear_model, preprocessing, metrics, tree

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("online-learn")

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
TOPIC           = "sensor.features"
GROUP_ID        = "online-learner"
MODEL_PATH      = os.path.join(os.getenv("ARTIFACT_DIR", "artifacts"), "online_model.pkl")

FEATURES = [
    "temperature", "humidity", "wind_speed", "irradiance",
    "hour", "day_of_week", "month", "is_weekend",
    "load_kw_mean_15m", "solar_kw_mean_15m",
    "temperature_mean_1h", "price_per_kwh",
]


def build_pipeline():
    return (
        preprocessing.StandardScaler()
        | linear_model.LinearRegression(
            intercept_lr=0.01,
            optimizer=None,   # uses default SGD
        )
    )


def load_or_create_model():
    if os.path.exists(MODEL_PATH):
        with open(MODEL_PATH, "rb") as f:
            model = pickle.load(f)
        log.info("Loaded online model from %s", MODEL_PATH)
    else:
        model = build_pipeline()
        log.info("Created new online model (LinearRegression / River)")
    return model


def save_model(model):
    os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)


def main():
    model  = load_or_create_model()
    metric = metrics.RMSE()

    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id":          GROUP_ID,
        "auto.offset.reset": "latest",
    })
    consumer.subscribe([TOPIC])
    log.info("Online learner started. Consuming '%s' ...", TOPIC)

    msg_count = 0
    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() != KafkaError._PARTITION_EOF:
                    log.error("Kafka error: %s", msg.error())
                continue

            try:
                record = json.loads(msg.value())
                x = {f: float(record.get(f, 0.0) or 0.0) for f in FEATURES}
                y = float(record.get("load_kw", 0.0))

                if y == 0.0:
                    continue

                y_pred = model.predict_one(x)
                model.learn_one(x, y)
                metric.update(y, y_pred)

                msg_count += 1
                if msg_count % 1000 == 0:
                    log.info("Messages: %d | RMSE: %.4f", msg_count, metric.get())
                    save_model(model)

            except Exception as exc:
                log.exception("Online learning error: %s", exc)
    finally:
        consumer.close()
        save_model(model)


if __name__ == "__main__":
    main()


"""
AEGIS – Digital Twin Data Generator
====================================
Generates one year of 1-minute resolution synthetic microgrid data for:
  - 3 buildings: residential, commercial, industrial
  - Solar PV generation (physics-based model)
  - Battery storage (SoC simulation)
  - Weather: temperature, humidity, wind speed, irradiance
  - Day-ahead electricity pricing (synthetic)

Outputs:
  - data/processed/microgrid_<year>.parquet
  - Inserts into TimescaleDB grid_readings table
"""

import os
import math
import random
import asyncio
import logging
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("digital-twin")

# ── Configuration ────────────────────────────────────────────
START_DATE = os.getenv("SIMULATION_START_DATE", "2024-01-01")
END_DATE   = os.getenv("SIMULATION_END_DATE",   "2024-12-31")
DB_DSN     = (
    f"postgresql://{os.getenv('POSTGRES_USER','aegis')}:"
    f"{os.getenv('POSTGRES_PASSWORD','aegis_secret')}@"
    f"{os.getenv('POSTGRES_HOST','timescaledb')}:"
    f"{os.getenv('POSTGRES_PORT','5432')}/"
    f"{os.getenv('POSTGRES_DB','aegis')}"
)

BUILDINGS = [
    {"node_id": "residential_01", "type": "residential",  "base_load_kw": 50},
    {"node_id": "commercial_01",  "type": "commercial",   "base_load_kw": 200},
    {"node_id": "industrial_01",  "type": "industrial",   "base_load_kw": 800},
]

SOLAR_CAPACITY_KW = 150.0   # PV array capacity
BATTERY_CAPACITY_KWH = 200.0
BATTERY_INITIAL_SOC  = 0.5  # 50 %


# ── Physics helpers ──────────────────────────────────────────

def solar_irradiance(dt: datetime, latitude: float = 23.0) -> float:
    """Compute approximate GHI (W/m²) using a simplified astronomical model."""
    day_of_year = dt.timetuple().tm_yday
    hour        = dt.hour + dt.minute / 60.0

    # Solar declination
    declination = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
    # Hour angle
    hour_angle  = (hour - 12) * 15
    lat_rad     = math.radians(latitude)
    dec_rad     = math.radians(declination)
    ha_rad      = math.radians(hour_angle)

    cos_zenith  = (
        math.sin(lat_rad) * math.sin(dec_rad)
        + math.cos(lat_rad) * math.cos(dec_rad) * math.cos(ha_rad)
    )
    cos_zenith  = max(0.0, cos_zenith)

    # Clear-sky GHI (simplified Ineichen-ish, no real AM calc)
    ghi = 1000.0 * cos_zenith
    # Add cloud randomness (correlated per day)
    random.seed(day_of_year)
    cloud_factor = random.uniform(0.4, 1.0)
    return ghi * cloud_factor * max(0.0, 1.0 - 0.05 * random.gauss(0, 1))


def temperature_profile(dt: datetime) -> float:
    """Synthetic temperature with seasonal + diurnal variation (°C)."""
    doy   = dt.timetuple().tm_yday
    hour  = dt.hour + dt.minute / 60.0
    t_mean_annual = 22.0
    t_amplitude   = 8.0   # seasonal
    t_diurnal     = 5.0   # diurnal
    seasonal = t_amplitude * math.sin(math.radians((doy - 80) / 365 * 360))
    diurnal  = t_diurnal  * math.sin(math.radians((hour - 6) / 24 * 360))
    return t_mean_annual + seasonal + diurnal + random.gauss(0, 0.5)


def load_profile(dt: datetime, building: dict) -> float:
    """Building load (kW) with occupancy, seasonal, and random factors."""
    hour      = dt.hour
    weekday   = dt.weekday()  # 0=Mon, 6=Sun
    base      = building["base_load_kw"]
    btype     = building["type"]

    # Occupancy factor
    if btype == "residential":
        occ = 0.6 if 0 <= hour < 7 else (1.0 if 18 <= hour < 23 else 0.4)
        occ *= 1.1 if weekday >= 5 else 1.0
    elif btype == "commercial":
        occ = 0.1 if hour < 7 or hour >= 20 else (0.9 if 9 <= hour < 18 else 0.5)
        occ *= 0.2 if weekday >= 5 else 1.0
    else:  # industrial
        occ = 0.95 if 6 <= hour < 22 else 0.4
        occ *= 0.6 if weekday >= 5 else 1.0

    # Seasonal AC factor
    doy      = dt.timetuple().tm_yday
    season   = 0.3 * math.sin(math.radians((doy - 172) / 365 * 360))

    load = base * occ * (1 + season) * max(0.5, random.gauss(1.0, 0.05))
    return max(0.0, load)


def price_profile(dt: datetime) -> float:
    """Day-ahead price ($/MWh) – synthetic TOU tariff."""
    hour = dt.hour
    if 9 <= hour < 12 or 17 <= hour < 21:
        base_price = 120.0   # peak
    elif 0 <= hour < 6:
        base_price = 40.0    # off-peak
    else:
        base_price = 75.0    # shoulder
    return base_price * max(0.7, random.gauss(1.0, 0.1))


# ── Main generation ──────────────────────────────────────────

def generate_records():
    """Generate all rows as a list of dicts."""
    log.info("Generating digital twin data from %s to %s ...", START_DATE, END_DATE)
    start = datetime.strptime(START_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end   = datetime.strptime(END_DATE,   "%Y-%m-%d").replace(tzinfo=timezone.utc)

    records     = []
    battery_soc = BATTERY_INITIAL_SOC

    dt = start
    while dt <= end:
        ghi        = solar_irradiance(dt)
        temp       = temperature_profile(dt)
        humidity   = max(20, min(100, 65 + 15 * math.sin(math.radians(dt.timetuple().tm_yday)) + random.gauss(0, 5)))
        wind_speed = max(0, 8 + 4 * math.sin(math.radians(dt.hour * 15)) + random.gauss(0, 2))
        price      = price_profile(dt)
        solar_kw   = SOLAR_CAPACITY_KW * (ghi / 1000) * 0.18  # 18 % efficiency

        # Battery simple SoC model: charge when solar excess, discharge at peak
        total_load = sum(load_profile(dt, b) for b in BUILDINGS)
        net_power  = solar_kw - total_load / len(BUILDINGS)   # simplified
        charge_kw  = min(50.0, max(-50.0, net_power * 0.5))
        delta_soc   = charge_kw / BATTERY_CAPACITY_KWH / 60   # 1-min step
        battery_soc = max(0.1, min(0.95, battery_soc + delta_soc))

        # Occasionally inject anomalies (< 0.2 % of rows)
        anomaly = random.random() < 0.002
        volt_pu = random.uniform(0.80, 0.90) if anomaly else random.gauss(1.0, 0.005)
        freq_hz = random.uniform(48.5, 49.0) if anomaly else random.gauss(50.0, 0.05)

        for building in BUILDINGS:
            records.append({
                "time":          dt,
                "node_id":       building["node_id"],
                "building_type": building["type"],
                "temperature":   round(temp, 2),
                "humidity":      round(humidity, 2),
                "wind_speed":    round(wind_speed, 2),
                "irradiance":    round(ghi, 2),
                "load_kw":       round(load_profile(dt, building), 2),
                "solar_kw":      round(solar_kw, 2),
                "battery_soc":   round(battery_soc, 4),
                "voltage_pu":    round(volt_pu, 4),
                "frequency_hz":  round(freq_hz, 4),
                "price_per_kwh": round(price / 1000, 5),
            })

        dt += timedelta(minutes=1)

    log.info("Generated %d records.", len(records))
    return records


async def insert_to_db(records: list):
    """Batch-insert records into TimescaleDB."""
    log.info("Connecting to TimescaleDB at %s ...", DB_DSN)
    conn = await asyncpg.connect(DB_DSN)
    try:
        log.info("Inserting %d rows in batches ...", len(records))
        batch_size = 5000
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            await conn.executemany(
                """
                INSERT INTO grid_readings
                  (time, node_id, building_type, temperature, humidity, wind_speed,
                   irradiance, load_kw, solar_kw, battery_soc, voltage_pu, frequency_hz, price_per_kwh)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
                ON CONFLICT DO NOTHING
                """,
                [
                    (
                        r["time"], r["node_id"], r["building_type"],
                        r["temperature"], r["humidity"], r["wind_speed"],
                        r["irradiance"], r["load_kw"], r["solar_kw"],
                        r["battery_soc"], r["voltage_pu"], r["frequency_hz"],
                        r["price_per_kwh"],
                    )
                    for r in batch
                ],
            )
            log.info("  Inserted rows %d – %d", i, i + len(batch))
    finally:
        await conn.close()
    log.info("DB insertion complete.")


def save_parquet(records: list):
    """Save records to Parquet file for AI training."""
    df = pd.DataFrame(records)
    df["time"] = pd.to_datetime(df["time"])
    # Save to the mounted data volume at /app/data/processed/
    out_path = os.path.join(os.path.dirname(__file__), "data", "processed", "microgrid_2024.parquet")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.to_parquet(out_path, index=False)
    log.info("Saved Parquet to %s  (shape=%s)", out_path, df.shape)


async def main():
    parquet_path = os.path.join(os.path.dirname(__file__), "data", "processed", "microgrid_2024.parquet")
    if os.path.exists(parquet_path):
        log.info("Parquet already exists at %s — loading from disk.", parquet_path)
        import pandas as _pd
        records_df = _pd.read_parquet(parquet_path)
        records = records_df.to_dict("records")
    else:
        records = generate_records()
        save_parquet(records)

    try:
        await insert_to_db(records)
    except Exception as exc:
        log.warning("DB insert skipped (not critical): %s", exc)

    log.info("Digital twin generation finished.")


if __name__ == "__main__":
    asyncio.run(main())


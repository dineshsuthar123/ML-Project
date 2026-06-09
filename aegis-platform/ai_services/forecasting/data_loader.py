"""
AEGIS – Forecasting Service: Data Loader
==========================================
Auto-detects column names (case-insensitive), loads CSV or Parquet,
and exposes a unified DataFrame API used by all AI services.
Maintains backward compatibility with the original project's data.csv.
"""

import os
import logging
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

log = logging.getLogger("data_loader")

# Column aliases (lower-case → canonical name)
COLUMN_ALIASES = {
    "temp":        "temperature",
    "tmp":         "temperature",
    "temperature": "temperature",
    "hum":         "humidity",
    "humidity":    "humidity",
    "wind":        "wind_speed",
    "wind_speed":  "wind_speed",
    "windspeed":   "wind_speed",
    "load":        "load_kw",
    "load_kw":     "load_kw",
    "electricity_load": "load_kw",
    "demand":      "load_kw",
    "solar":       "solar_kw",
    "solar_kw":    "solar_kw",
    "pv":          "solar_kw",
    "irr":         "irradiance",
    "irradiance":  "irradiance",
    "ghi":         "irradiance",
    "soc":         "battery_soc",
    "battery_soc": "battery_soc",
    "price":       "price_per_kwh",
    "price_per_kwh": "price_per_kwh",
    "volt":        "voltage_pu",
    "voltage":     "voltage_pu",
    "voltage_pu":  "voltage_pu",
    "freq":        "frequency_hz",
    "frequency":   "frequency_hz",
    "frequency_hz": "frequency_hz",
}

DATETIME_KEYWORDS = ["date", "time", "timestamp", "datetime", "dt"]


def _normalize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Rename columns to canonical names using aliases."""
    rename_map = {}
    for col in df.columns:
        key = col.strip().lower().replace(" ", "_")
        if key in COLUMN_ALIASES:
            rename_map[col] = COLUMN_ALIASES[key]
    if rename_map:
        log.info("Column rename map: %s", rename_map)
        df = df.rename(columns=rename_map)
    return df


def _find_datetime_column(df: pd.DataFrame) -> Optional[str]:
    """Detect datetime column by name heuristics."""
    for col in df.columns:
        if any(kw in col.lower() for kw in DATETIME_KEYWORDS):
            return col
    return None


def _extract_time_features(df: pd.DataFrame, dt_col: str) -> pd.DataFrame:
    """Parse datetime and extract hour, day, month, day_of_week, is_weekend."""
    df[dt_col] = pd.to_datetime(df[dt_col], errors="coerce")
    df["hour"]        = df[dt_col].dt.hour
    df["day"]         = df[dt_col].dt.day
    df["month"]       = df[dt_col].dt.month
    df["day_of_week"] = df[dt_col].dt.dayofweek
    df["is_weekend"]  = (df["day_of_week"] >= 5).astype(int)
    df["week_of_year"] = df[dt_col].dt.isocalendar().week.astype(int)
    return df


def load_dataframe(path: str, target_col: str = "load_kw") -> pd.DataFrame:
    """
    Load a CSV or Parquet file, normalize columns, extract time features,
    and return a clean DataFrame ready for model training.

    Parameters
    ----------
    path       : path to CSV or Parquet file
    target_col : canonical name of the target variable

    Returns
    -------
    pd.DataFrame with normalized columns and time features
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Data file not found: {path}")

    log.info("Loading data from %s ...", path)
    if p.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path)

    log.info("Loaded shape: %s", df.shape)
    df = _normalize_column_names(df)

    dt_col = _find_datetime_column(df)
    if dt_col:
        log.info("Datetime column detected: '%s'", dt_col)
        df = _extract_time_features(df, dt_col)
    else:
        log.warning("No datetime column found; time features will be absent.")

    df = df.dropna(subset=[target_col])
    df = df.replace([np.inf, -np.inf], np.nan).dropna()
    log.info("Clean shape after dropna: %s", df.shape)
    return df


def get_feature_columns(df: pd.DataFrame, target_col: str = "load_kw") -> list[str]:
    """
    Return a list of numeric feature columns (excluding the target and
    non-numeric columns).
    """
    exclude = {target_col, "time", "node_id", "building_type", "published_at"}
    candidates = [
        c for c in df.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c])
    ]
    return candidates


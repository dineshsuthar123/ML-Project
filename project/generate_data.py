"""
Generate a synthetic weather + electricity load dataset.
Run this once to create data.csv, then delete this file if you want.
"""
import pandas as pd
import numpy as np

np.random.seed(42)

# Generate 8760 rows (one year of hourly data)
hours = 8760
date_range = pd.date_range(start="2024-01-01", periods=hours, freq="h")

temperature = 15 + 15 * np.sin(2 * np.pi * (np.arange(hours) - 3 * 30 * 24) / (365 * 24)) \
              + np.random.normal(0, 3, hours)

humidity = 60 + 20 * np.sin(2 * np.pi * np.arange(hours) / (365 * 24) + 1) \
           + np.random.normal(0, 5, hours)
humidity = np.clip(humidity, 10, 100)

wind_speed = 8 + np.random.exponential(3, hours)
wind_speed = np.clip(wind_speed, 0, 40)

# Electricity load depends on temperature, humidity, hour-of-day, and some noise
hour_of_day = date_range.hour
month = date_range.month

# Base load + temperature effect + humidity effect + time-of-day pattern + noise
base_load = 500
temp_effect = 8 * (temperature - 20) ** 2 / 10  # higher load when very hot or cold
humidity_effect = 0.5 * humidity
hour_effect = 100 * np.sin(np.pi * (hour_of_day - 6) / 12)  # peaks midday
noise = np.random.normal(0, 30, hours)

load = base_load + temp_effect + humidity_effect + hour_effect + noise
load = np.clip(load, 100, None)  # load can't go below 100

df = pd.DataFrame({
    "datetime": date_range,
    "temperature": np.round(temperature, 1),
    "humidity": np.round(humidity, 1),
    "wind_speed": np.round(wind_speed, 1),
    "load": np.round(load, 1)
})

df.to_csv("data.csv", index=False)
print(f"Dataset created: {len(df)} rows saved to data.csv")
print(df.head())


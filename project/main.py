"""
Weather-Based Electricity Load Forecasting Using Machine Learning
=================================================================
A simple ML project that predicts electricity load from weather and time features.
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error
import joblib
import os

# --------------------------------------------------
# 1. Load dataset
# --------------------------------------------------
DATA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.csv")
print("Loading dataset...")
df = pd.read_csv(DATA_PATH)
print(f"Dataset shape: {df.shape}")
print(df.head())

# --------------------------------------------------
# 2. Convert datetime column
# --------------------------------------------------
# Auto-detect datetime column (first column that parses as datetime)
datetime_col = None
for col in df.columns:
    if "date" in col.lower() or "time" in col.lower():
        datetime_col = col
        break

if datetime_col is None:
    # try first column
    datetime_col = df.columns[0]

df[datetime_col] = pd.to_datetime(df[datetime_col])
print(f"\nDatetime column used: '{datetime_col}'")

# --------------------------------------------------
# 3. Create time features: hour, day, month
# --------------------------------------------------
df["hour"] = df[datetime_col].dt.hour
df["day"] = df[datetime_col].dt.day
df["month"] = df[datetime_col].dt.month

# --------------------------------------------------
# 4. Handle missing values
# --------------------------------------------------
before = len(df)
df.dropna(inplace=True)
after = len(df)
if before != after:
    print(f"Dropped {before - after} rows with missing values.")

# --------------------------------------------------
# 5. Select features and target
# --------------------------------------------------
# Auto-detect column names (handle slight naming differences)
def find_col(df, candidates):
    """Find a column matching any of the candidate names (case-insensitive)."""
    for c in candidates:
        for col in df.columns:
            if col.lower().replace("_", "").replace(" ", "") == c.lower().replace("_", ""):
                return col
    return None

temp_col = find_col(df, ["temperature", "temp", "Temperature"])
hum_col = find_col(df, ["humidity", "Humidity", "relative_humidity"])
wind_col = find_col(df, ["wind_speed", "windspeed", "Wind_Speed", "wind"])
load_col = find_col(df, ["load", "Load", "electricity_load", "demand", "power"])

print(f"\nFeature columns detected:")
print(f"  Temperature : {temp_col}")
print(f"  Humidity    : {hum_col}")
print(f"  Wind Speed  : {wind_col}")
print(f"  Load (target): {load_col}")

feature_cols = ["hour", "day", "month"]
rename_map = {}

for original, name in [(temp_col, "temperature"), (hum_col, "humidity"), (wind_col, "wind_speed")]:
    if original and original != name:
        rename_map[original] = name
    if original:
        feature_cols.insert(0, name)

if rename_map:
    df.rename(columns=rename_map, inplace=True)

if load_col and load_col != "load":
    df.rename(columns={load_col: "load"}, inplace=True)

X = df[feature_cols]
y = df["load"]

print(f"\nFeatures used: {feature_cols}")
print(f"Target: load")
print(f"X shape: {X.shape}, y shape: {y.shape}")

# --------------------------------------------------
# 6. Train/test split
# --------------------------------------------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
print(f"\nTrain size: {X_train.shape[0]}, Test size: {X_test.shape[0]}")

# --------------------------------------------------
# 7. Train model (RandomForestRegressor, fallback to LinearRegression)
# --------------------------------------------------
print("\nTraining RandomForestRegressor...")
try:
    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    model_name = "RandomForestRegressor"
except Exception as e:
    print(f"RandomForest failed ({e}), falling back to LinearRegression...")
    model = LinearRegression()
    model.fit(X_train, y_train)
    model_name = "LinearRegression"

print(f"Model used: {model_name}")

# --------------------------------------------------
# 8. Evaluate using RMSE
# --------------------------------------------------
y_pred = model.predict(X_test)
rmse = np.sqrt(mean_squared_error(y_test, y_pred))
print(f"\n{'='*40}")
print(f"  RMSE: {rmse:.2f}")
print(f"{'='*40}")

# --------------------------------------------------
# 9. Save model
# --------------------------------------------------
MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "model.pkl")
joblib.dump(model, MODEL_PATH)
print(f"\nModel saved to: {MODEL_PATH}")

# --------------------------------------------------
# 10. Sample prediction
# --------------------------------------------------
sample = X_test.iloc[[0]]
actual = y_test.iloc[0]
predicted = model.predict(sample)[0]

print(f"\n--- Sample Prediction ---")
print(f"Input features:\n{sample.to_string(index=False)}")
print(f"Actual load   : {actual:.2f}")
print(f"Predicted load: {predicted:.2f}")
print(f"\nDone! Project ran successfully.")


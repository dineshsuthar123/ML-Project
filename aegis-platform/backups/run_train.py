"""Quick training runner — patches DATA_PATH then runs train.py."""
import sys, os

# Point to the parquet we copied into the container
DATA_PATH_OVERRIDE = "/app/microgrid_2024.parquet"

# Monkey-patch before importing train
import importlib, types
import train as _train_mod
_train_mod.DATA_PATH = DATA_PATH_OVERRIDE
_train_mod.LEGACY_CSV = DATA_PATH_OVERRIDE

class FakeArgs:
    epochs  = int(os.getenv("EPOCHS", "25"))
    seq_len = int(os.getenv("SEQ_LEN", "60"))
    horizon = int(os.getenv("HORIZON", "24"))

from data_loader import load_dataframe
print(f"Loading data from {DATA_PATH_OVERRIDE}")
df = load_dataframe(DATA_PATH_OVERRIDE)
print(f"Loaded {len(df)} rows, columns: {list(df.columns)}")

print("=== Training baseline RandomForest ===")
rf = _train_mod.train_baseline_rf(df)
print("RF done:", rf)

print("=== Training TCN Forecaster ===")
tcn = _train_mod.train_tcn(df, FakeArgs())
print("TCN done:", tcn)
print("All training complete!")


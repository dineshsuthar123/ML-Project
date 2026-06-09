"""
AEGIS – Forecasting Service: Training Script
=============================================
Trains AEGISForecaster (TCN + Attention) on the digital twin Parquet.
Also trains the legacy RandomForest baseline for paper comparison.

Usage:
    python train.py [--epochs 50] [--seq-len 60] [--horizon 24]
"""

import os
import json
import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
from sklearn.preprocessing import StandardScaler
import joblib

from model import AEGISForecaster, PinballLoss
from data_loader import load_dataframe, get_feature_columns

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train")

ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "artifacts")
Path(ARTIFACT_DIR).mkdir(parents=True, exist_ok=True)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "processed", "microgrid_2024.parquet")
LEGACY_CSV = os.path.join(os.path.dirname(__file__), "..", "..", "..", "project", "data.csv")

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ── Dataset ──────────────────────────────────────────────────

class SequenceDataset(Dataset):
    def __init__(self, X: np.ndarray, y: np.ndarray, seq_len: int, horizon: int):
        self.X       = torch.tensor(X, dtype=torch.float32)
        self.y       = torch.tensor(y, dtype=torch.float32)
        self.seq_len = seq_len
        self.horizon = horizon

    def __len__(self):
        return len(self.X) - self.seq_len - self.horizon + 1

    def __getitem__(self, idx):
        x_seq = self.X[idx : idx + self.seq_len]
        y_seq = self.y[idx + self.seq_len : idx + self.seq_len + self.horizon]
        return x_seq, y_seq


# ── Training loop ────────────────────────────────────────────

def train_tcn(df: pd.DataFrame, args) -> dict:
    feature_cols = get_feature_columns(df, "load_kw")
    target_col   = "load_kw"

    scaler_X = StandardScaler()
    scaler_y = StandardScaler()

    X = scaler_X.fit_transform(df[feature_cols].values)
    y = scaler_y.fit_transform(df[[target_col]].values).ravel()

    split = int(len(X) * 0.8)
    train_ds = SequenceDataset(X[:split],  y[:split],  args.seq_len, args.horizon)
    val_ds   = SequenceDataset(X[split:],  y[split:],  args.seq_len, args.horizon)

    train_loader = DataLoader(train_ds, batch_size=64, shuffle=True,  num_workers=0)
    val_loader   = DataLoader(val_ds,   batch_size=64, shuffle=False, num_workers=0)

    model     = AEGISForecaster(input_size=len(feature_cols), horizon=args.horizon).to(DEVICE)
    criterion = PinballLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)

    best_val_loss = float("inf")
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for xb, yb in train_loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            optimizer.zero_grad()
            preds = model(xb)
            loss  = criterion(preds, yb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
        scheduler.step()

        # Validation
        model.eval()
        val_loss = 0.0
        all_preds, all_targets = [], []
        with torch.no_grad():
            for xb, yb in val_loader:
                xb, yb = xb.to(DEVICE), yb.to(DEVICE)
                preds = model(xb)
                val_loss += criterion(preds, yb).item()
                all_preds.append(preds["q50"].cpu().numpy())
                all_targets.append(yb.cpu().numpy())

        val_loss /= max(1, len(val_loader))
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), os.path.join(ARTIFACT_DIR, "forecaster.pt"))
            log.info("Epoch %3d | train=%.4f | val=%.4f  ← saved best", epoch, total_loss / len(train_loader), val_loss)
        elif epoch % 10 == 0:
            log.info("Epoch %3d | train=%.4f | val=%.4f", epoch, total_loss / len(train_loader), val_loss)

    # Compute final metrics
    all_preds   = np.concatenate(all_preds).ravel()
    all_targets = np.concatenate(all_targets).ravel()
    all_preds   = scaler_y.inverse_transform(all_preds.reshape(-1, 1)).ravel()
    all_targets = scaler_y.inverse_transform(all_targets.reshape(-1, 1)).ravel()

    rmse = float(np.sqrt(mean_squared_error(all_targets, all_preds)))
    mae  = float(mean_absolute_error(all_targets, all_preds))
    r2   = float(r2_score(all_targets, all_preds))

    # Save scalers and metadata
    joblib.dump(scaler_X, os.path.join(ARTIFACT_DIR, "scaler_X.pkl"))
    joblib.dump(scaler_y, os.path.join(ARTIFACT_DIR, "scaler_y.pkl"))

    meta = {
        "model":         "AEGISForecaster_TCN_Attention",
        "feature_cols":  feature_cols,
        "seq_len":       args.seq_len,
        "horizon":       args.horizon,
        "rmse":          rmse,
        "mae":           mae,
        "r2":            r2,
    }
    with open(os.path.join(ARTIFACT_DIR, "forecaster_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    log.info("TCN Forecaster – RMSE=%.4f  MAE=%.4f  R²=%.4f", rmse, mae, r2)
    return meta


def train_baseline_rf(df: pd.DataFrame) -> dict:
    """Train legacy RandomForest (baseline for paper comparison)."""
    feature_cols = get_feature_columns(df, "load_kw")
    X = df[feature_cols].values
    y = df["load_kw"].values
    split = int(len(X) * 0.8)

    model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
    model.fit(X[:split], y[:split])
    preds = model.predict(X[split:])

    rmse = float(np.sqrt(mean_squared_error(y[split:], preds)))
    mae  = float(mean_absolute_error(y[split:], preds))
    r2   = float(r2_score(y[split:], preds))

    joblib.dump(model, os.path.join(ARTIFACT_DIR, "baseline_rf.pkl"))
    meta = {"model": "RandomForestRegressor", "rmse": rmse, "mae": mae, "r2": r2}

    with open(os.path.join(ARTIFACT_DIR, "baseline_rf_meta.json"), "w") as f:
        json.dump(meta, f, indent=2)

    log.info("Baseline RF     – RMSE=%.4f  MAE=%.4f  R²=%.4f", rmse, mae, r2)
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs",  type=int, default=50)
    parser.add_argument("--seq-len", type=int, default=60)
    parser.add_argument("--horizon", type=int, default=24)
    args = parser.parse_args()

    # Prefer digital-twin data, fall back to legacy CSV
    data_path = DATA_PATH if Path(DATA_PATH).exists() else LEGACY_CSV
    log.info("Using data: %s", data_path)

    df = load_dataframe(data_path)

    log.info("=== Training baseline RandomForest ===")
    rf_meta = train_baseline_rf(df)

    log.info("=== Training TCN + Attention Forecaster ===")
    tcn_meta = train_tcn(df, args)

    log.info("Training complete.")
    log.info("RF  metrics: %s", rf_meta)
    log.info("TCN metrics: %s", tcn_meta)


if __name__ == "__main__":
    main()


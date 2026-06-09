"""Train VAE anomaly detector on real microgrid data."""
import os, json, logging
import numpy as np
import torch
import joblib
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("vae-train")

from vae_model import GridVAE, vae_loss
from sklearn.preprocessing import StandardScaler

ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "artifacts")
Path(ARTIFACT_DIR).mkdir(parents=True, exist_ok=True)
DEVICE = torch.device("cpu")  # CPU is fine for VAE

VAE_FEATURES = [
    "voltage_pu", "frequency_hz", "load_kw", "solar_kw",
    "battery_soc", "temperature", "humidity", "wind_speed",
]

parquet = Path("/app/microgrid_2024.parquet")
if not parquet.exists():
    log.error("Parquet not found at %s", parquet)
    exit(1)

import pandas as pd
log.info("Loading parquet...")
df = pd.read_parquet(parquet)[VAE_FEATURES].dropna()
log.info("Total rows: %d", len(df))

# Filter normal operating conditions for training
df_normal = df[
    (df["voltage_pu"] > 0.93) & (df["voltage_pu"] < 1.07) &
    (df["frequency_hz"] > 49.5) & (df["frequency_hz"] < 50.5)
]
log.info("Normal rows for training: %d  (%.1f%%)", len(df_normal), 100*len(df_normal)/len(df))

scaler = StandardScaler()
X = scaler.fit_transform(df_normal.values.astype(np.float32))

# Sample 100k rows for faster training
if len(X) > 100_000:
    idx = np.random.choice(len(X), 100_000, replace=False)
    X = X[idx]
    log.info("Sampled 100k rows for training")

X_t = torch.tensor(X, dtype=torch.float32).to(DEVICE)

vae = GridVAE(input_dim=len(VAE_FEATURES)).to(DEVICE)
optimizer = torch.optim.Adam(vae.parameters(), lr=1e-3)

vae.train()
for epoch in range(30):
    perm = torch.randperm(len(X_t))
    total = 0.0
    for i in range(0, len(X_t), 512):
        batch = X_t[perm[i:i+512]]
        optimizer.zero_grad()
        x_hat, mu, lv = vae(batch)
        loss = vae_loss(batch, x_hat, mu, lv)
        loss.backward()
        optimizer.step()
        total += loss.item()
    if (epoch+1) % 5 == 0:
        log.info("VAE Epoch %2d | loss=%.6f", epoch+1, total/max(1, len(X_t)//512))

vae.eval()
# Compute threshold = 99th percentile of reconstruction errors on training set
with torch.no_grad():
    errors = []
    for i in range(0, len(X_t), 1024):
        batch = X_t[i:i+1024]
        e = vae.reconstruction_error(batch).cpu().numpy()
        errors.extend(e.tolist())

threshold = float(np.percentile(errors, 99))
vae.threshold = threshold
log.info("VAE threshold (99th pct): %.6f", threshold)

# Save
torch.save(vae.state_dict(), Path(ARTIFACT_DIR) / "vae.pt")
joblib.dump(scaler, Path(ARTIFACT_DIR) / "vae_scaler.pkl")
with open(Path(ARTIFACT_DIR) / "vae_threshold.json", "w") as f:
    json.dump({"threshold": threshold, "features": VAE_FEATURES}, f, indent=2)

log.info("VAE saved to %s", ARTIFACT_DIR)
print("DONE. Threshold =", threshold)


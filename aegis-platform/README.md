# ⚡ AEGIS – Autonomous Energy Grid Intelligent System

> **Production-grade, research-ready intelligent microgrid platform** with hybrid AI control, real-time demand response, and self-healing infrastructure.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-Compose-blue.svg)](docker-compose.yml)
[![Python](https://img.shields.io/badge/Python-3.11-green.svg)](https://python.org)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://reactjs.org)

---

## 🗺️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        AEGIS Platform                               │
│                                                                     │
│  Digital Twin ──► Kafka (KRaft) ──► Stream Processor               │
│       │                │                    │                       │
│       │           sensor.raw          sensor.features               │
│       │                                     │                       │
│       └──────► TimescaleDB     ┌────────────┼─────────────┐         │
│                                ▼            ▼             ▼         │
│                           Forecasting   Anomaly       RL Agent      │
│                            (TCN+Attn)   (VAE+Rules)   (SAC)         │
│                                │            │             │         │
│                                └────────────┴─────────────┘         │
│                                             │                       │
│                                      API Gateway                    │
│                                      (FastAPI + JWT)                │
│                                      WebSocket /ws/                 │
│                                             │                       │
│                                    React Dashboard                  │
│                              (MUI + Recharts + D3)                  │
│                                                                     │
│  Prometheus ──► Grafana          MinIO (model artifacts)            │
│  Redis (cache)                   Kafka UI (debug)                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Docker Desktop (Windows/Mac/Linux) or Docker Engine + Compose Plugin
- 8 GB RAM recommended (all services combined)
- Ports available: 3000, 3001, 8000-8004, 8080, 9000-9001, 9090, 5432, 6379

### 1. Clone and start

```bash
git clone <repo-url> aegis-platform
cd aegis-platform

# Copy environment file (already pre-filled with defaults)
cp .env .env.local   # optionally edit secrets

# Start all infrastructure + services
docker compose up -d

# Watch logs
docker compose logs -f
```

### 2. Generate training data (one-time)

The `digital-twin` service runs automatically on first `docker compose up`.
To run it manually:

```bash
docker compose run --rm digital-twin
```

This generates ~1.5M rows of synthetic microgrid data and inserts into TimescaleDB + saves to `data/processed/microgrid_2024.parquet`.

### 3. Train AI models

```bash
# Train TCN forecaster + RandomForest baseline
docker compose run --rm forecasting python train.py --epochs 50

# Train SAC RL agent (100k steps, ~10 min on CPU)
docker compose run --rm rl-agent python train_agent.py --timesteps 100000
```

The anomaly VAE trains automatically on first service start from the Parquet data.

### 4. Open the dashboard

| Service        | URL                         | Credentials     |
|----------------|-----------------------------|-----------------|
| **AEGIS Dashboard** | http://localhost:3000  | –               |
| **API Docs**   | http://localhost:8000/docs  | –               |
| **Kafka UI**   | http://localhost:8080       | –               |
| **MinIO**      | http://localhost:9001       | minioadmin / minioadmin |
| **Grafana**    | http://localhost:3001       | admin / admin   |
| **Prometheus** | http://localhost:9090       | –               |

---

## 📂 Project Structure

```
aegis-platform/
├── docker-compose.yml          # Full stack orchestration
├── .env                        # Environment variables
├── Makefile                    # Convenience targets
├── data/
│   ├── generate_digital_twin.py  # Synthetic microgrid data generator
│   └── processed/              # Parquet files (generated)
├── streaming/
│   ├── sensor_simulator.py     # Publishes Parquet → Kafka
│   └── stream_processors/
│       └── feature_engineering.py  # Rolling window features
├── ai_services/
│   ├── forecasting/            # TCN+Attention probabilistic forecaster
│   │   ├── model.py            # PyTorch model definition
│   │   ├── train.py            # Training script
│   │   ├── online_learn.py     # River incremental learning
│   │   ├── data_loader.py      # Auto-column-detect data loader
│   │   └── serve.py            # FastAPI service (port 8001)
│   ├── anomaly_detection/      # VAE + causal rules
│   │   ├── vae_model.py        # Variational Autoencoder
│   │   ├── causal_rules.py     # Expert rule engine
│   │   └── serve.py            # FastAPI service (port 8002)
│   ├── rl_agent/               # SAC battery dispatch agent
│   │   ├── env.py              # Custom Gymnasium environment
│   │   ├── train_agent.py      # SAC training with SB3
│   │   ├── safety_gate.py      # Hard constraint enforcement
│   │   └── policy_server.py    # FastAPI service (port 8003)
│   └── demand_response/        # OR-Tools CP-SAT optimizer
│       ├── optimizer.py        # CP-SAT formulation
│       └── serve.py            # FastAPI service (port 8004)
├── control_plane/
│   ├── rule_engine.py          # State machine (NORMAL/PEAK/EMERGENCY)
│   └── device_connector.py     # Simulated device communication
├── api_gateway/                # Unified FastAPI gateway (port 8000)
│   ├── main.py
│   ├── websocket_manager.py    # Kafka → WebSocket broadcast
│   └── routes/
│       ├── forecast.py
│       ├── anomaly.py
│       ├── control.py          # JWT-auth operator commands
│       └── dashboard.py
├── frontend/                   # React + Vite + MUI dashboard
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   │   ├── SingleLineDiagram.jsx   # SVG microgrid topology
│   │   │   ├── ForecastChart.jsx       # Recharts quantile chart
│   │   │   ├── AnomalyAlertPanel.jsx   # Real-time alerts
│   │   │   ├── WhatIfSimulator.jsx     # Interactive simulation
│   │   │   └── OperatorOverride.jsx    # Manual dispatch
│   │   └── hooks/
│   │       └── useWebSocket.js         # WS hook with auto-reconnect
│   └── nginx.conf              # Nginx reverse proxy config
├── monitoring/
│   ├── prometheus.yml          # Scrape config for all services
│   └── grafana_dashboards/     # Pre-built Grafana JSON
├── research/
│   ├── paper_draft.md          # ACM/IEEE paper outline
│   └── experiments.ipynb       # Ablation study notebook
└── infra/
    └── init.sql                # TimescaleDB schema + hypertables
```

---

## 🤖 AI Models

### 1. TCN + Attention Forecaster (`ai_services/forecasting/`)
- **Architecture**: Dilated causal CNN (4 blocks) + multi-head self-attention
- **Output**: Probabilistic forecast – quantiles q10, q50, q90 for next 24 steps
- **Training**: Pinball loss, AdamW, cosine annealing LR
- **API**: `POST /forecast` with weather + time features

### 2. GridVAE Anomaly Detector (`ai_services/anomaly_detection/`)
- **Architecture**: Encoder-Decoder VAE, 8-dim latent space
- **Threshold**: 99th percentile of training reconstruction error
- **Diagnosis**: Causal rule engine with 8 prioritized rules
- **Streaming**: Consumes `sensor.features`, publishes to `anomaly.alerts`

### 3. SAC Battery Agent (`ai_services/rl_agent/`)
- **Algorithm**: Soft Actor-Critic (off-policy, continuous actions)
- **Environment**: Custom Gymnasium with 6-dim obs, scalar action
- **Safety**: Hard-constraint gate checks SoC, voltage, rate-of-change
- **Explainability**: SHAP KernelExplainer for action attribution

### 4. CP-SAT Demand Response (`ai_services/demand_response/`)
- **Solver**: Google OR-Tools CP-SAT
- **Objective**: Minimize total discomfort cost
- **Constraint**: Total allocation ≥ required curtailment
- **Time limit**: 5 seconds with proportional fallback

---

## 🔐 Authentication

Operator endpoints (`/api/control/*`) require JWT authentication:

```bash
# Get token (demo credentials)
curl -X POST http://localhost:8000/api/control/token \
  -d "username=admin&password=admin123"

# Use token
curl -H "Authorization: Bearer <token>" \
  -X POST http://localhost:8000/api/control/manual \
  -H "Content-Type: application/json" \
  -d '{"device_id":"commercial_01","command_type":"discharge","value_kw":30}'
```

---

## 📊 API Reference

Full interactive documentation: **http://localhost:8000/docs**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/forecast` | POST | Probabilistic 24-h load forecast |
| `/api/forecast/history` | GET | Past forecasts vs actuals |
| `/api/anomalies` | GET | Recent anomaly alerts |
| `/api/anomalies/score` | POST | Score a single telemetry record |
| `/api/control/rl-action` | POST | RL agent battery dispatch action |
| `/api/control/manual` | POST | Operator manual override (auth) |
| `/api/control/status` | GET | Recent control log |
| `/api/demand-response` | POST | Run DR optimization |
| `/api/latest-telemetry` | GET | Latest sensor readings |
| `/api/dashboard/summary` | GET | KPI summary for all nodes |
| `/api/dashboard/timeseries` | GET | Bucketed time-series for charting |
| `/ws/live-telemetry` | WS | Real-time sensor + prediction stream |

---

## 🧪 Research & Experiments

The Jupyter notebook `research/experiments.ipynb` provides:
- Baseline RandomForest training and evaluation on original `data.csv`
- Comparison of TCN-Attn vs RF vs online learner (RMSE, MAE, R², pinball loss)
- VAE anomaly detector precision/recall on injected fault dataset
- RL agent cumulative reward curves vs rule-based controller
- Ablation study tables
- Diebold-Mariano test for forecast model comparison

To run:
```bash
cd research
pip install jupyter scikit-learn pandas numpy matplotlib seaborn torch
jupyter notebook experiments.ipynb
```

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Kafka not starting | Ensure `CLUSTER_ID` in `.env` matches the value in `docker-compose.yml` |
| TimescaleDB init fails | Run `docker compose down -v` and `docker compose up -d` again |
| Model not loaded (503) | Run `docker compose run --rm forecasting python train.py` first |
| Frontend shows blank page | Wait for `api-gateway` to be healthy, then refresh |
| Port conflict | Edit port mappings in `docker-compose.yml` |
| `model.pkl not found` (legacy) | Run `cd project && python main.py` for the original project |

---

## 📜 License

MIT License – free for academic and commercial use.  
All dependencies are free and open-source (Apache 2.0, MIT, BSD).

---

## 📚 Citation

If you use AEGIS in your research, please cite:

```bibtex
@software{aegis2026,
  title  = {AEGIS: Autonomous Energy Grid Intelligent System},
  author = {Author, Name},
  year   = {2026},
  url    = {https://github.com/aegis-platform/aegis},
  note   = {Open-source microgrid intelligence platform}
}
```

---

**Last Updated**: May 2026 | **Status**: ✅ Complete and Runnable


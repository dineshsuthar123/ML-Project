-- ============================================================
-- AEGIS – TimescaleDB Initialization Script
-- ============================================================

-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;

-- ── Grid Sensor Readings (hypertable) ──────────────────────
CREATE TABLE IF NOT EXISTS grid_readings (
    time          TIMESTAMPTZ       NOT NULL,
    node_id       TEXT              NOT NULL,
    building_type TEXT              NOT NULL DEFAULT 'unknown',
    temperature   DOUBLE PRECISION,
    humidity      DOUBLE PRECISION,
    wind_speed    DOUBLE PRECISION,
    irradiance    DOUBLE PRECISION,
    load_kw       DOUBLE PRECISION,
    solar_kw      DOUBLE PRECISION,
    battery_soc   DOUBLE PRECISION,
    voltage_pu    DOUBLE PRECISION  DEFAULT 1.0,
    frequency_hz  DOUBLE PRECISION  DEFAULT 50.0,
    price_per_kwh DOUBLE PRECISION
);

SELECT create_hypertable('grid_readings', 'time', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS idx_grid_readings_node ON grid_readings (node_id, time DESC);

-- ── Forecast Results ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forecast_results (
    time          TIMESTAMPTZ       NOT NULL,
    node_id       TEXT              NOT NULL,
    horizon_hours INTEGER           NOT NULL,
    q10           DOUBLE PRECISION,
    q50           DOUBLE PRECISION,
    q90           DOUBLE PRECISION,
    model_version TEXT              DEFAULT 'v1'
);

SELECT create_hypertable('forecast_results', 'time', if_not_exists => TRUE);

-- ── Anomaly Alerts ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS anomaly_alerts (
    time             TIMESTAMPTZ    NOT NULL,
    node_id          TEXT           NOT NULL,
    severity         TEXT           NOT NULL,  -- LOW / MEDIUM / HIGH / CRITICAL
    reconstruction_error DOUBLE PRECISION,
    diagnosis        TEXT,
    acknowledged     BOOLEAN        DEFAULT FALSE
);

SELECT create_hypertable('anomaly_alerts', 'time', if_not_exists => TRUE);

-- ── Control Log ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS control_log (
    time          TIMESTAMPTZ       NOT NULL,
    source        TEXT              NOT NULL,  -- rl_agent / operator / dr_optimizer
    device_id     TEXT              NOT NULL,
    command_type  TEXT              NOT NULL,  -- charge / discharge / curtail / shed_load
    value         DOUBLE PRECISION,
    approved      BOOLEAN           DEFAULT TRUE,
    safety_override BOOLEAN         DEFAULT FALSE,
    notes         TEXT
);

SELECT create_hypertable('control_log', 'time', if_not_exists => TRUE);

-- ── RL Agent Episodes ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS rl_episodes (
    time          TIMESTAMPTZ       NOT NULL,
    episode_id    INTEGER           NOT NULL,
    step          INTEGER           NOT NULL,
    state_soc     DOUBLE PRECISION,
    state_load    DOUBLE PRECISION,
    state_solar   DOUBLE PRECISION,
    state_price   DOUBLE PRECISION,
    action        DOUBLE PRECISION,
    reward        DOUBLE PRECISION,
    cumulative_reward DOUBLE PRECISION
);

SELECT create_hypertable('rl_episodes', 'time', if_not_exists => TRUE);

-- ── Demand Response Schedule ────────────────────────────────
CREATE TABLE IF NOT EXISTS dr_schedules (
    time            TIMESTAMPTZ     NOT NULL,
    participant_id  TEXT            NOT NULL,
    required_curtailment_kw DOUBLE PRECISION,
    allocated_kw    DOUBLE PRECISION,
    accepted        BOOLEAN         DEFAULT FALSE
);

SELECT create_hypertable('dr_schedules', 'time', if_not_exists => TRUE);

-- ── Users (for JWT auth) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL PRIMARY KEY,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT        NOT NULL,
    role          TEXT        NOT NULL DEFAULT 'operator',
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default admin user (password: admin123)
INSERT INTO users (username, password_hash, role)
VALUES ('admin', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKAQnCKAtDpLGQi', 'admin')
ON CONFLICT (username) DO NOTHING;

COMMENT ON TABLE grid_readings IS 'Real-time sensor telemetry from simulated microgrid nodes';
COMMENT ON TABLE forecast_results IS 'Probabilistic load/generation forecasts (quantiles)';
COMMENT ON TABLE anomaly_alerts IS 'Detected anomalies with diagnosis from VAE + rule engine';
COMMENT ON TABLE control_log IS 'All control commands sent to devices (RL, DR, operator)';


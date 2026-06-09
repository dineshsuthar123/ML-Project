"""
AEGIS – RL Agent: Microgrid Gymnasium Environment
===================================================
Custom Gym environment simulating a microgrid with:
  - State : [battery_soc, load_kw (norm), solar_kw (norm), price (norm), hour_sin, hour_cos]
  - Action: continuous scalar in [-1, 1]
             > 0 → charge at rate action * MAX_CHARGE_KW
             < 0 → discharge at rate |action| * MAX_DISCHARGE_KW
  - Reward : profit from energy arbitrage minus constraint violation penalties

The environment steps 1 minute at a time, optionally backed by
real digital-twin data (Parquet) or a simple synthetic sine model.
"""

import os
import math
import random
from pathlib import Path
from typing import Optional

import numpy as np
import gymnasium as gym
from gymnasium import spaces


class MicrogridEnv(gym.Env):
    """
    Microgrid battery dispatch environment.

    Observation space (6 dims):
      [battery_soc, load_norm, solar_norm, price_norm, hour_sin, hour_cos]

    Action space: Box(-1, 1) shape (1,)
      +1 = max charge, -1 = max discharge
    """

    metadata = {"render_modes": ["human"]}

    # ── Physical constants ──────────────────────────────
    BATTERY_CAPACITY_KWH = 200.0
    MAX_CHARGE_KW        = 50.0
    MAX_DISCHARGE_KW     = 50.0
    SOC_MIN              = 0.10
    SOC_MAX              = 0.95
    STEP_HOURS           = 1 / 60   # 1-minute steps
    MAX_LOAD_KW          = 1200.0
    MAX_SOLAR_KW         = 150.0
    MAX_PRICE            = 0.20     # $/kWh

    def __init__(self, data_path: Optional[str] = None, max_steps: int = 1440):
        super().__init__()
        self.max_steps = max_steps

        # Load or generate data
        if data_path and Path(data_path).exists():
            import pandas as pd
            df = pd.read_parquet(data_path)
            df = df[df["node_id"] == "commercial_01"].sort_values("time").reset_index(drop=True)
            self._load_series  = df["load_kw"].fillna(200.0).values.astype(np.float32)
            self._solar_series = df["solar_kw"].fillna(0.0).values.astype(np.float32)
            self._price_series = df["price_per_kwh"].fillna(0.08).values.astype(np.float32)
            self._hours        = df["time"].apply(
                lambda t: int(str(t).split("T")[1].split(":")[0]) if "T" in str(t) else 0
            ).values
            self._use_data = True
        else:
            self._use_data = False

        self.observation_space = spaces.Box(
            low=-1.0, high=1.0, shape=(6,), dtype=np.float32
        )
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(1,), dtype=np.float32)

        self._step    = 0
        self._offset  = 0
        self._soc     = 0.5
        self._cumulative_reward = 0.0

    # ── Helpers ─────────────────────────────────────────

    def _get_context(self):
        if self._use_data:
            idx   = (self._offset + self._step) % len(self._load_series)
            load  = float(self._load_series[idx])
            solar = float(self._solar_series[idx])
            price = float(self._price_series[idx])
            hour  = int(self._hours[idx])
        else:
            hour  = (self._step // 60) % 24
            load  = 200 + 100 * math.sin(math.pi * hour / 12)
            solar = max(0, 150 * math.sin(math.pi * (hour - 6) / 12)) if 6 <= hour <= 18 else 0.0
            price = 0.12 if 9 <= hour < 12 or 17 <= hour < 21 else 0.04 if hour < 6 else 0.08
        return load, solar, price, hour

    def _obs(self, load, solar, price, hour):
        return np.array([
            self._soc * 2 - 1,   # map [0,1] → [-1,1]
            load  / self.MAX_LOAD_KW  * 2 - 1,
            solar / self.MAX_SOLAR_KW * 2 - 1,
            price / self.MAX_PRICE    * 2 - 1,
            math.sin(2 * math.pi * hour / 24),
            math.cos(2 * math.pi * hour / 24),
        ], dtype=np.float32)

    # ── Gym API ─────────────────────────────────────────

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self._step = 0
        self._soc  = random.uniform(0.3, 0.7)
        self._cumulative_reward = 0.0
        if self._use_data:
            self._offset = random.randint(0, max(0, len(self._load_series) - self.max_steps - 1))
        load, solar, price, hour = self._get_context()
        return self._obs(load, solar, price, hour), {}

    def step(self, action: np.ndarray):
        action = float(np.clip(action, -1.0, 1.0))
        load, solar, price, hour = self._get_context()

        # Power balance (positive = charging battery)
        if action >= 0:
            delta_kw = action * self.MAX_CHARGE_KW
        else:
            delta_kw = action * self.MAX_DISCHARGE_KW  # negative = discharge

        # Update SoC
        delta_soc = delta_kw * self.STEP_HOURS / self.BATTERY_CAPACITY_KWH
        new_soc   = self._soc + delta_soc

        # Safety violations
        violated = False
        if new_soc < self.SOC_MIN:
            new_soc  = self.SOC_MIN
            violated = True
        elif new_soc > self.SOC_MAX:
            new_soc  = self.SOC_MAX
            violated = True

        # Reward: profit from discharging at high price, minus charging cost
        energy_kwh  = abs(delta_kw) * self.STEP_HOURS
        profit      = -delta_kw * price * self.STEP_HOURS   # discharge is negative delta
        penalty     = -5.0 if violated else 0.0

        reward = profit + penalty
        self._soc  = new_soc
        self._step += 1

        obs   = self._obs(load, solar, price, hour)
        done  = self._step >= self.max_steps
        self._cumulative_reward += reward

        info = {
            "soc":         self._soc,
            "load_kw":     load,
            "solar_kw":    solar,
            "price":       price,
            "action":      action,
            "profit":      profit,
            "violated":    violated,
            "cum_reward":  self._cumulative_reward,
        }
        return obs, reward, done, False, info

    def render(self):
        load, solar, price, hour = self._get_context()
        print(f"Step={self._step:4d} | SoC={self._soc:.2f} | "
              f"Load={load:.1f}kW | Solar={solar:.1f}kW | "
              f"Price={price:.4f}$/kWh | CumRew={self._cumulative_reward:.2f}")


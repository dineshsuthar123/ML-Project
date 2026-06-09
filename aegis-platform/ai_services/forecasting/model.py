"""
AEGIS – Forecasting Service: TCN + Attention Model
====================================================
Temporal Convolutional Network with multi-head self-attention for
probabilistic (quantile) 24-hour ahead load forecasting.

Architecture:
  - Input: sequence of L time steps × F features
  - TCN backbone: 4 dilated causal conv blocks
  - Multi-head self-attention over TCN output
  - Three output heads (q10, q50, q90) for uncertainty quantification

References:
  Bai et al. (2018) – An Empirical Evaluation of Generic Convolutional
  and Recurrent Networks for Sequence Modeling
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


# ── Dilated Causal Conv Block ────────────────────────────────

class CausalConv1d(nn.Module):
    """1-D convolution that pads left to maintain causal alignment."""

    def __init__(self, in_ch: int, out_ch: int, kernel_size: int, dilation: int):
        super().__init__()
        self.padding = (kernel_size - 1) * dilation
        self.conv = nn.Conv1d(
            in_ch, out_ch, kernel_size,
            padding=self.padding, dilation=dilation
        )

    def forward(self, x):
        out = self.conv(x)
        return out[:, :, : x.size(2)]   # trim right padding


class TCNBlock(nn.Module):
    def __init__(self, channels: int, kernel_size: int, dilation: int, dropout: float = 0.1):
        super().__init__()
        self.net = nn.Sequential(
            CausalConv1d(channels, channels, kernel_size, dilation),
            nn.BatchNorm1d(channels),
            nn.GELU(),
            nn.Dropout(dropout),
            CausalConv1d(channels, channels, kernel_size, dilation),
            nn.BatchNorm1d(channels),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.residual = nn.Identity()

    def forward(self, x):
        return F.gelu(self.net(x) + self.residual(x))


# ── Positional Encoding ──────────────────────────────────────

class PositionalEncoding(nn.Module):
    def __init__(self, d_model: int, max_len: int = 512):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        pos = torch.arange(max_len).unsqueeze(1).float()
        div = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(pos * div)
        pe[:, 1::2] = torch.cos(pos * div)
        self.register_buffer("pe", pe.unsqueeze(0))   # (1, max_len, d_model)

    def forward(self, x):
        # x: (B, T, d_model)
        return x + self.pe[:, : x.size(1)]


# ── Main Model ───────────────────────────────────────────────

class AEGISForecaster(nn.Module):
    """
    TCN + Multi-Head Attention quantile forecaster.

    Parameters
    ----------
    input_size   : number of input features
    hidden_size  : internal channel dimension
    num_blocks   : number of dilated TCN blocks
    kernel_size  : convolution kernel size
    nhead        : number of attention heads
    dropout      : dropout rate
    horizon      : forecast horizon in steps (default 24 for 1-hour res.)
    quantiles    : output quantile levels
    """

    def __init__(
        self,
        input_size:  int   = 16,
        hidden_size: int   = 64,
        num_blocks:  int   = 4,
        kernel_size: int   = 3,
        nhead:       int   = 4,
        dropout:     float = 0.1,
        horizon:     int   = 24,
        quantiles:   list  = None,
    ):
        super().__init__()
        if quantiles is None:
            quantiles = [0.1, 0.5, 0.9]
        self.horizon   = horizon
        self.quantiles = quantiles
        self.n_q       = len(quantiles)

        # Input projection
        self.input_proj = nn.Linear(input_size, hidden_size)

        # TCN backbone (4 blocks with exponential dilation)
        self.tcn = nn.Sequential(
            *[TCNBlock(hidden_size, kernel_size, 2 ** i, dropout)
              for i in range(num_blocks)]
        )

        # Self-attention over time
        self.pos_enc  = PositionalEncoding(hidden_size)
        self.attn     = nn.MultiheadAttention(hidden_size, nhead, dropout=dropout, batch_first=True)
        self.attn_norm = nn.LayerNorm(hidden_size)

        # Quantile output heads
        self.heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(hidden_size, hidden_size),
                nn.GELU(),
                nn.Linear(hidden_size, horizon),
            )
            for _ in quantiles
        ])

    def forward(self, x: torch.Tensor) -> dict[str, torch.Tensor]:
        """
        Parameters
        ----------
        x : (B, T, F) – batch of input sequences

        Returns
        -------
        dict with keys 'q10', 'q50', 'q90' each of shape (B, horizon)
        """
        # (B, T, F) → (B, F, T) for conv
        h = self.input_proj(x).permute(0, 2, 1)
        h = self.tcn(h)
        h = h.permute(0, 2, 1)   # → (B, T, hidden)

        # Self-attention
        h_pe  = self.pos_enc(h)
        h_att, _ = self.attn(h_pe, h_pe, h_pe)
        h     = self.attn_norm(h + h_att)

        # Use last time step as context vector
        ctx = h[:, -1, :]   # (B, hidden)

        outputs = {}
        q_names = [f"q{int(q*100):02d}" for q in self.quantiles]
        for name, head in zip(q_names, self.heads):
            outputs[name] = head(ctx)   # (B, horizon)

        return outputs


# ── Quantile / Pinball Loss ──────────────────────────────────

class PinballLoss(nn.Module):
    """Combined pinball loss across all quantiles."""

    def __init__(self, quantiles: list = None):
        super().__init__()
        if quantiles is None:
            quantiles = [0.1, 0.5, 0.9]
        self.quantiles = quantiles

    def forward(self, predictions: dict, targets: torch.Tensor) -> torch.Tensor:
        """
        predictions : dict {q_name: (B, horizon)}
        targets     : (B, horizon)
        """
        total = 0.0
        q_names = [f"q{int(q*100):02d}" for q in self.quantiles]
        for q, name in zip(self.quantiles, q_names):
            pred = predictions[name]
            err  = targets - pred
            loss = torch.max(q * err, (q - 1) * err)
            total = total + loss.mean()
        return total / len(self.quantiles)


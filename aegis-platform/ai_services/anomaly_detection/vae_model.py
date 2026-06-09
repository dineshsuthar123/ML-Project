"""
AEGIS – Anomaly Detection: Variational Autoencoder
====================================================
VAE trained on normal grid operating data (voltage, frequency, load, solar).
Reconstruction error → anomaly score.  Threshold set at training time as
the 99th percentile of training reconstruction errors.

Reference:
  Kingma & Welling (2013) – Auto-Encoding Variational Bayes
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class VAEEncoder(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int, latent_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.GELU(),
        )
        self.mu_head      = nn.Linear(hidden_dim // 2, latent_dim)
        self.log_var_head = nn.Linear(hidden_dim // 2, latent_dim)

    def forward(self, x):
        h = self.net(x)
        return self.mu_head(h), self.log_var_head(h)


class VAEDecoder(nn.Module):
    def __init__(self, latent_dim: int, hidden_dim: int, output_dim: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(latent_dim, hidden_dim // 2),
            nn.GELU(),
            nn.Linear(hidden_dim // 2, hidden_dim),
            nn.LayerNorm(hidden_dim),
            nn.GELU(),
            nn.Linear(hidden_dim, output_dim),
        )

    def forward(self, z):
        return self.net(z)


class GridVAE(nn.Module):
    """
    Variational Autoencoder for grid telemetry anomaly detection.

    Parameters
    ----------
    input_dim  : number of telemetry features
    hidden_dim : encoder/decoder hidden units
    latent_dim : latent space dimension
    """

    def __init__(self, input_dim: int = 8, hidden_dim: int = 64, latent_dim: int = 8):
        super().__init__()
        self.encoder = VAEEncoder(input_dim, hidden_dim, latent_dim)
        self.decoder = VAEDecoder(latent_dim, hidden_dim, input_dim)
        self.threshold: float = 0.0   # set after training

    def reparameterize(self, mu: torch.Tensor, log_var: torch.Tensor) -> torch.Tensor:
        std = torch.exp(0.5 * log_var)
        eps = torch.randn_like(std)
        return mu + eps * std

    def forward(self, x: torch.Tensor):
        mu, log_var = self.encoder(x)
        z           = self.reparameterize(mu, log_var)
        x_hat       = self.decoder(z)
        return x_hat, mu, log_var

    def reconstruction_error(self, x: torch.Tensor) -> torch.Tensor:
        """Return per-sample MSE reconstruction error (no grad)."""
        with torch.no_grad():
            x_hat, _, _ = self.forward(x)
            return F.mse_loss(x_hat, x, reduction="none").mean(dim=1)

    def is_anomaly(self, x: torch.Tensor) -> torch.Tensor:
        """Boolean mask: True = anomaly."""
        return self.reconstruction_error(x) > self.threshold


def vae_loss(x: torch.Tensor, x_hat: torch.Tensor,
             mu: torch.Tensor, log_var: torch.Tensor,
             beta: float = 1.0) -> torch.Tensor:
    """β-VAE ELBO loss: reconstruction + KL divergence."""
    recon = F.mse_loss(x_hat, x, reduction="mean")
    kl    = -0.5 * torch.mean(1 + log_var - mu.pow(2) - log_var.exp())
    return recon + beta * kl


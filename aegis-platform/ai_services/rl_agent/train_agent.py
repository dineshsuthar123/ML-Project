"""
AEGIS – RL Agent: SAC Training Script
=======================================
Trains a Soft Actor-Critic (SAC) agent using stable-baselines3
on the MicrogridEnv.  Saves policy to artifacts/ and MinIO.

Usage:
    python train_agent.py [--timesteps 500000]
"""

import os
import argparse
import logging
from pathlib import Path

from stable_baselines3 import SAC
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
from stable_baselines3.common.monitor import Monitor

from env import MicrogridEnv

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("train-agent")

ARTIFACT_DIR = os.getenv("ARTIFACT_DIR", "artifacts")
DATA_DIR     = Path(os.getenv("AEGIS_DATA_DIR", Path(__file__).resolve().parents[2] / "data")).resolve()
DATA_PATH    = DATA_DIR / "processed" / "microgrid_2024.parquet"
Path(ARTIFACT_DIR).mkdir(parents=True, exist_ok=True)


def make_env():
    env = MicrogridEnv(data_path=DATA_PATH if Path(DATA_PATH).exists() else None)
    return Monitor(env)


def train(timesteps: int = 300_000, progress_bar: bool = False):
    train_env = make_vec_env(make_env, n_envs=4)
    eval_env  = make_env()

    model = SAC(
        "MlpPolicy",
        train_env,
        verbose=1,
        learning_rate=3e-4,
        buffer_size=100_000,
        batch_size=256,
        tau=0.005,
        gamma=0.99,
        train_freq=1,
        gradient_steps=1,
        tensorboard_log=os.path.join(ARTIFACT_DIR, "tb_logs"),
    )

    callbacks = [
        EvalCallback(
            eval_env,
            best_model_save_path=ARTIFACT_DIR,
            log_path=ARTIFACT_DIR,
            eval_freq=10_000,
            deterministic=True,
            verbose=1,
        ),
        CheckpointCallback(
            save_freq=50_000,
            save_path=os.path.join(ARTIFACT_DIR, "checkpoints"),
            name_prefix="sac_microgrid",
        ),
    ]

    log.info("Training SAC for %d timesteps ...", timesteps)
    model.learn(total_timesteps=timesteps, callback=callbacks, progress_bar=progress_bar)

    final_path = os.path.join(ARTIFACT_DIR, "sac_final")
    model.save(final_path)
    log.info("Model saved to %s", final_path)

    # Try to upload to MinIO
    try:
        import boto3
        s3 = boto3.client(
            "s3",
            endpoint_url=f"http://{os.getenv('MINIO_ENDPOINT','localhost:9000')}",
            aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
            aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        )
        bucket = os.getenv("MINIO_BUCKET", "aegis-models")
        s3.upload_file(final_path + ".zip", bucket, "rl_agent/sac_final.zip")
        log.info("Uploaded to MinIO bucket '%s'", bucket)
    except Exception as exc:
        log.warning("MinIO upload skipped: %s", exc)

    return model


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=300_000)
    parser.add_argument("--progress-bar", action="store_true")
    args = parser.parse_args()
    train(args.timesteps, progress_bar=args.progress_bar)


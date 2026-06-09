from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("torch")

from train import SequenceDataset, train_tcn


def test_sequence_dataset_length_matches_window_count():
    X = np.zeros((20, 3), dtype=np.float32)
    y = np.zeros(20, dtype=np.float32)

    ds = SequenceDataset(X, y, seq_len=5, horizon=3)

    assert len(ds) == 13


def test_train_tcn_rejects_too_little_data():
    df = pd.DataFrame(
        {
            "load_kw": [1.0, 2.0, 3.0, 4.0],
            "temperature": [20.0, 21.0, 22.0, 23.0],
            "humidity": [50.0, 51.0, 52.0, 53.0],
        }
    )
    args = SimpleNamespace(seq_len=3, horizon=2, epochs=1, batch_size=2)

    with pytest.raises(ValueError, match="Not enough rows"):
        train_tcn(df, args)


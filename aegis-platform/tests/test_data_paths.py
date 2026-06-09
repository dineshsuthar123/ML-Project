import importlib
from pathlib import Path

import pytest

pytest.importorskip("asyncpg")
pytest.importorskip("pandas")


def test_digital_twin_uses_configured_data_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))

    import generate_digital_twin

    module = importlib.reload(generate_digital_twin)

    assert module.DATA_DIR == tmp_path.resolve()
    assert module.PARQUET_PATH == tmp_path.resolve() / "processed" / "microgrid_2024.parquet"


def test_digital_twin_defaults_to_repo_data_directory(monkeypatch):
    monkeypatch.delenv("AEGIS_DATA_DIR", raising=False)

    import generate_digital_twin

    module = importlib.reload(generate_digital_twin)

    assert module.PARQUET_PATH == Path(module.__file__).resolve().parent / "processed" / "microgrid_2024.parquet"


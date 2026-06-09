import pytest

from main import _cors_origins as gateway_cors_origins
from serve import _cors_origins as demand_response_cors_origins


@pytest.mark.parametrize("cors_func", [gateway_cors_origins, demand_response_cors_origins])
def test_cors_origin_parser_trims_configured_origins(monkeypatch, cors_func):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", " https://app.example.com, http://localhost:3000 ")
    monkeypatch.setitem(cors_func.__globals__, "APP_ENV", "production")

    assert cors_func() == ["https://app.example.com", "http://localhost:3000"]


@pytest.mark.parametrize("cors_func", [gateway_cors_origins, demand_response_cors_origins])
def test_wildcard_cors_is_rejected_in_production(monkeypatch, cors_func):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "*")
    monkeypatch.setitem(cors_func.__globals__, "APP_ENV", "production")

    with pytest.raises(RuntimeError, match="CORS_ALLOW_ORIGINS"):
        cors_func()

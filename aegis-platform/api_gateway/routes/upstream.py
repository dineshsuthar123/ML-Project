"""Reliable JSON proxying helpers for API gateway routes."""

from typing import Any

import httpx
from fastapi import HTTPException


async def request_json(
    method: str,
    url: str,
    *,
    timeout: float,
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> Any:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.request(method, url, params=params, json=json)
    except httpx.TimeoutException as exc:
        raise HTTPException(504, f"Upstream service timed out: {url}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(503, f"Upstream service unavailable: {url}") from exc

    if not response.is_success:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text or "Upstream service request failed"
        raise HTTPException(response.status_code, detail)

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, "Upstream service returned invalid JSON") from exc

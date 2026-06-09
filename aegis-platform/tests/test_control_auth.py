import asyncio

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jose")
pytest.importorskip("passlib")

from jose import jwt
from routes.control import JWT_ALGORITHM, JWT_SECRET, create_token, get_current_user


def test_create_token_can_be_decoded_by_gateway_auth():
    token = create_token({"sub": "operator-1", "role": "admin"})

    assert asyncio.run(get_current_user(token)) == "operator-1"


def test_token_without_subject_is_rejected():
    token = jwt.encode({"role": "admin"}, JWT_SECRET, algorithm=JWT_ALGORITHM)

    with pytest.raises(Exception):
        asyncio.run(get_current_user(token))


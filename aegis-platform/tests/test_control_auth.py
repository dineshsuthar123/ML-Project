import asyncio
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("jose")
pytest.importorskip("passlib")

from jose import jwt
from routes.control import (
    JWT_ALGORITHM,
    JWT_SECRET,
    ManualCommandIn,
    create_token,
    get_current_user,
    manual_command,
)


def test_create_token_can_be_decoded_by_gateway_auth():
    token = create_token({"sub": "operator-1", "role": "admin"})

    assert asyncio.run(get_current_user(token)) == "operator-1"


def test_token_without_subject_is_rejected():
    token = jwt.encode({"role": "admin"}, JWT_SECRET, algorithm=JWT_ALGORITHM)

    with pytest.raises(Exception):
        asyncio.run(get_current_user(token))


class FakeProducer:
    def __init__(self):
        self.messages = []

    async def send_and_wait(self, topic, value, key):
        self.messages.append((topic, json.loads(value), key))


def test_manual_command_is_queued_for_control_plane():
    producer = FakeProducer()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(kafka_producer=producer)))
    command = ManualCommandIn(
        device_id="commercial_01",
        command_type="discharge",
        value_kw=30,
        notes="test",
    )

    result = asyncio.run(manual_command(command, request, user="operator-1"))

    assert result["status"] == "queued"
    assert producer.messages[0][0] == "control.commands"
    assert producer.messages[0][1]["operator"] == "operator-1"
    assert producer.messages[0][2] == b"commercial_01"


def test_manual_command_rejects_invalid_power_before_queueing():
    producer = FakeProducer()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(kafka_producer=producer)))
    command = ManualCommandIn(
        device_id="commercial_01",
        command_type="charge",
        value_kw=0,
    )

    with pytest.raises(Exception):
        asyncio.run(manual_command(command, request, user="operator-1"))

    assert producer.messages == []


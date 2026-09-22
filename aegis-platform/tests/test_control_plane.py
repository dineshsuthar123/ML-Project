import pytest

pytest.importorskip("confluent_kafka")

from rule_engine import GridState, RuleEngine


class RecordingConnector:
    def __init__(self):
        self.commands = []

    def send_command(self, *args, **kwargs):
        self.commands.append((args, kwargs))


def make_engine():
    engine = RuleEngine()
    engine.connector = RecordingConnector()
    return engine


def test_manual_command_reaches_connector_when_allowed():
    engine = make_engine()

    accepted = engine.process_manual_command({
        "device_id": "commercial_01",
        "command_type": "discharge",
        "value_kw": 30,
        "operator": "operator-1",
        "notes": "peak reduction",
    })

    assert accepted is True
    assert engine.connector.commands[0][0] == ("commercial_01", "discharge", 30.0)
    assert engine.connector.commands[0][1]["source"] == "operator"


def test_manual_command_is_blocked_by_emergency_state():
    engine = make_engine()
    engine.state = GridState.EMERGENCY

    accepted = engine.process_manual_command({
        "device_id": "commercial_01",
        "command_type": "charge",
        "value_kw": 30,
    })

    assert accepted is False
    assert engine.connector.commands == []


@pytest.mark.parametrize("value", [0, -1, 10_001, "invalid"])
def test_manual_command_rejects_invalid_power(value):
    engine = make_engine()

    accepted = engine.process_manual_command({
        "device_id": "commercial_01",
        "command_type": "shed_load",
        "value_kw": value,
    })

    assert accepted is False
    assert engine.connector.commands == []

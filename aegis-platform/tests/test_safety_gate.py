from safety_gate import apply_safety_gate
from env import MicrogridEnv


def test_low_soc_blocks_discharge():
    result = apply_safety_gate(action=-0.8, soc=0.2, voltage_pu=1.0)

    assert result.approved is False
    assert result.final_action == 0.0
    assert any("SOC_LOW" in violation for violation in result.violations)


def test_high_soc_blocks_charge():
    result = apply_safety_gate(action=0.8, soc=0.9, voltage_pu=1.0)

    assert result.approved is False
    assert result.final_action == 0.0
    assert any("SOC_HIGH" in violation for violation in result.violations)


def test_ramp_limit_scales_action_down():
    result = apply_safety_gate(action=0.8, soc=0.7, voltage_pu=1.0, prev_soc=0.5)

    assert result.approved is False
    assert result.final_action < 0.8
    assert any("RAMP_LIMIT" in violation for violation in result.violations)


def test_microgrid_env_accepts_vector_action_from_sb3():
    env = MicrogridEnv(max_steps=2)
    env.reset(seed=42)

    obs, reward, terminated, truncated, info = env.step([0.25])

    assert obs.shape == (6,)
    assert isinstance(float(reward), float)
    assert terminated is False
    assert truncated is False
    assert info["action"] == 0.25


import pytest

from radiant.fdir import (
    HealthSignal,
    HealthState,
    SystemHealthConfig,
    SystemHealthStateMachine,
)


def test_starts_normal():
    monitor = SystemHealthStateMachine()
    assert monitor.state is HealthState.NORMAL


def test_single_fault_enters_warning():
    monitor = SystemHealthStateMachine()
    result = monitor.evaluate([HealthSignal("sensor", "bias")])
    assert result.current is HealthState.WARNING


def test_persistent_fault_enters_degraded():
    monitor = SystemHealthStateMachine()
    signal = HealthSignal("transport", "gap")
    monitor.evaluate([signal])
    result = monitor.evaluate([signal])
    assert result.current is HealthState.DEGRADED


def test_persistent_fault_enters_safe():
    monitor = SystemHealthStateMachine()
    signal = HealthSignal("timing", "residual")
    states = [monitor.evaluate([signal]).current for _ in range(4)]
    assert states[-1] is HealthState.SAFE


def test_critical_signal_forces_safe_immediately():
    monitor = SystemHealthStateMachine()
    result = monitor.evaluate([HealthSignal("state", "mirror_failure", critical=True)])
    assert result.current is HealthState.SAFE


def test_severity_three_enters_degraded_immediately():
    monitor = SystemHealthStateMachine()
    result = monitor.evaluate([HealthSignal("timing", "freeze", severity=3)])
    assert result.current is HealthState.DEGRADED


def test_healthy_hysteresis_steps_down_one_state_at_a_time():
    monitor = SystemHealthStateMachine(SystemHealthConfig(recover_after=2))
    monitor.evaluate([HealthSignal("state", "fatal", critical=True)])
    assert monitor.state is HealthState.SAFE
    monitor.evaluate([])
    assert monitor.state is HealthState.SAFE
    monitor.evaluate([])
    assert monitor.state is HealthState.DEGRADED
    monitor.evaluate([])
    monitor.evaluate([])
    assert monitor.state is HealthState.WARNING
    monitor.evaluate([])
    monitor.evaluate([])
    assert monitor.state is HealthState.NORMAL


def test_clean_sample_resets_fault_streak():
    monitor = SystemHealthStateMachine()
    signal = HealthSignal("sensor", "noise")
    monitor.evaluate([signal])
    monitor.evaluate([])
    result = monitor.evaluate([signal])
    assert result.current is HealthState.WARNING
    assert result.fault_streak == 1


def test_reset_clears_state_and_history():
    monitor = SystemHealthStateMachine()
    monitor.evaluate([HealthSignal("sensor", "bias")])
    monitor.reset()
    assert monitor.state is HealthState.NORMAL
    assert monitor.history == []
    assert monitor.fault_streak == 0
    assert monitor.clean_streak == 0


def test_invalid_configuration_and_signals_rejected():
    with pytest.raises(ValueError):
        SystemHealthConfig(warning_after=3, degraded_after=2)
    with pytest.raises(ValueError):
        HealthSignal("", "bias")
    with pytest.raises(ValueError):
        HealthSignal("sensor", "bias", severity=4)
    monitor = SystemHealthStateMachine()
    with pytest.raises(TypeError):
        monitor.evaluate([object()])

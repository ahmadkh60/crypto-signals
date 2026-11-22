import pytest

from app.core.config import Settings


def test_strategy_settings_defaults():
    settings = Settings()

    assert settings.breakout_lookback == 20
    assert settings.pullback_atr_multiplier == 0.5
    assert settings.pullback_max_bars == 10


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_breakout_lookback(value):
    with pytest.raises(ValueError):
        Settings(breakout_lookback=value)


@pytest.mark.parametrize("value", [0, -0.5, float("inf"), float("nan"), True])
def test_invalid_pullback_atr_multiplier(value):
    with pytest.raises(ValueError):
        Settings(pullback_atr_multiplier=value)


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_pullback_max_bars(value):
    with pytest.raises(ValueError):
        Settings(pullback_max_bars=value)

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from app.market_data.pipeline import fetch_and_validate
from app.market_data.quality_gate import QualityGateConfig


def make_payload(timestamps=None, volumes=None):
    timestamps = timestamps or [1700000000, 1700014400]
    volumes = volumes or ["1", "2"]

    return {
        "s": "ok",
        "t": timestamps,
        "o": ["100", "105"],
        "h": ["110", "115"],
        "l": ["95", "100"],
        "c": ["105", "110"],
        "v": volumes,
    }


def make_quality_config():
    return QualityGateConfig(
        expected_interval=timedelta(hours=4),
        now=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_accepts_valid_market_data():
    with patch(
        "app.market_data.pipeline.fetch_history",
        return_value=make_payload(),
    ):
        result = fetch_and_validate(
            "BTCIRT",
            "240",
            1700000000,
            1700020000,
            make_quality_config(),
        )

    assert result.accepted is True
    assert result.symbol == "BTCIRT"
    assert len(result.candles["timestamp"]) == 2
    assert result.issues == ()


def test_rejects_market_data_with_candle_gap():
    with patch(
        "app.market_data.pipeline.fetch_history",
        return_value=make_payload(
            timestamps=[1700000000, 1700018000],
        ),
    ):
        result = fetch_and_validate(
            "BTCIRT",
            "240",
            1700000000,
            1700020000,
            make_quality_config(),
        )

    assert result.accepted is False
    assert any(issue.code == "CANDLE_GAP" for issue in result.issues)


def test_zero_volume_warning_does_not_reject_data():
    with patch(
        "app.market_data.pipeline.fetch_history",
        return_value=make_payload(volumes=["0", "2"]),
    ):
        result = fetch_and_validate(
            "BTCIRT",
            "240",
            1700000000,
            1700020000,
            make_quality_config(),
        )

    assert result.accepted is True
    assert any(issue.code == "ZERO_VOLUME" for issue in result.issues)
    assert all(issue.severity == "warning" for issue in result.issues)


def test_zero_volume_error_rejects_data():
    config = QualityGateConfig(
        expected_interval=timedelta(hours=4),
        now=datetime(2026, 1, 1, tzinfo=UTC),
        zero_volume_policy="error",
    )

    with patch(
        "app.market_data.pipeline.fetch_history",
        return_value=make_payload(volumes=["0", "2"]),
    ):
        result = fetch_and_validate(
            "BTCIRT",
            "240",
            1700000000,
            1700020000,
            config,
        )

    assert result.accepted is False
    assert any(issue.code == "ZERO_VOLUME" for issue in result.issues)

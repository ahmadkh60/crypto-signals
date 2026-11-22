import json
from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.core.config import Settings
from app.market_data.wallex import (
    WallexAPIError,
    fetch_history,
    normalize_symbol,
)


def make_settings():
    return Settings()


def mock_response(payload):
    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps(payload).encode()

    return Response()


def test_normalize_supported_symbols():
    assert normalize_symbol("BTCIRT") == "BTCTMN"
    assert normalize_symbol("ETHIRT") == "ETHTMN"
    assert normalize_symbol("BTCTMN") == "BTCTMN"


def test_rejects_unsupported_symbol():
    with pytest.raises(ValueError, match="Unsupported"):
        normalize_symbol("DOGEIRT")


def test_fetch_history_returns_raw_payload():
    payload = {
        "s": "ok",
        "t": [1700000000],
        "o": ["100"],
        "h": ["110"],
        "l": ["90"],
        "c": ["105"],
        "v": ["2"],
    }

    with patch(
        "app.market_data.wallex.urlopen",
        return_value=mock_response(payload),
    ) as mocked:
        result = fetch_history(
            "BTCIRT",
            "60",
            1700000000,
            1700003600,
            settings=make_settings(),
        )

    assert result == payload

    request = mocked.call_args.args[0]
    assert "symbol=BTCTMN" in request.full_url
    assert "resolution=60" in request.full_url
    assert "from=1700000000" in request.full_url
    assert "to=1700003600" in request.full_url


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (-1, 100),
        (100, 100),
        (200, 100),
        (True, 100),
        (100, False),
        (1.5, 100),
    ],
)
def test_rejects_invalid_time_range(start, end):
    with pytest.raises(ValueError):
        fetch_history(
            "BTCIRT",
            "60",
            start,
            end,
            settings=make_settings(),
        )


def test_rejects_empty_resolution():
    with pytest.raises(ValueError, match="resolution"):
        fetch_history(
            "BTCIRT",
            "",
            100,
            200,
            settings=make_settings(),
        )


def test_rejects_non_ok_api_status():
    with patch(
        "app.market_data.wallex.urlopen",
        return_value=mock_response({"s": "no_data"}),
    ):
        with pytest.raises(WallexAPIError, match="status"):
            fetch_history(
                "BTCIRT",
                "60",
                100,
                200,
                settings=make_settings(),
            )


def test_rejects_invalid_json():
    class Response(BytesIO):
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch(
        "app.market_data.wallex.urlopen",
        return_value=Response(b"not-json"),
    ):
        with pytest.raises(WallexAPIError, match="invalid JSON"):
            fetch_history(
                "BTCIRT",
                "60",
                100,
                200,
                settings=make_settings(),
            )


def test_rejects_non_object_json():
    with patch(
        "app.market_data.wallex.urlopen",
        return_value=mock_response(["not", "an", "object"]),
    ):
        with pytest.raises(WallexAPIError, match="JSON object"):
            fetch_history(
                "BTCIRT",
                "60",
                100,
                200,
                settings=make_settings(),
            )


def test_wraps_http_error():
    error = HTTPError(
        "https://api.wallex.ir",
        429,
        "Too Many Requests",
        {},
        None,
    )

    with patch(
        "app.market_data.wallex.urlopen",
        side_effect=error,
    ):
        with pytest.raises(WallexAPIError, match="HTTP error: 429"):
            fetch_history(
                "BTCIRT",
                "60",
                100,
                200,
                settings=make_settings(),
            )


def test_wraps_network_error():
    with patch(
        "app.market_data.wallex.urlopen",
        side_effect=URLError("connection failed"),
    ):
        with pytest.raises(WallexAPIError, match="Could not reach"):
            fetch_history(
                "BTCIRT",
                "60",
                100,
                200,
                settings=make_settings(),
            )

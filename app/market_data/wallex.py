from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core.config import Settings, get_settings


class WallexAPIError(RuntimeError):
    """Raised when the Wallex API request fails."""


SYMBOL_MAP = {
    "BTCIRT": "BTCTMN",
    "ETHIRT": "ETHTMN",
    "BTCTMN": "BTCTMN",
    "ETHTMN": "ETHTMN",
}


def normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()

    try:
        return SYMBOL_MAP[normalized]
    except KeyError:
        raise ValueError(f"Unsupported Wallex symbol: {symbol!r}") from None


def fetch_history(
    symbol: str,
    resolution: str,
    start: int,
    end: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Fetch raw historical candle data from Wallex UDF API."""
    if isinstance(start, bool) or not isinstance(start, int):
        raise ValueError("start must be an integer Unix timestamp.")

    if isinstance(end, bool) or not isinstance(end, int):
        raise ValueError("end must be an integer Unix timestamp.")

    if start < 0 or end <= start:
        raise ValueError("Invalid timestamp range.")

    if not isinstance(resolution, str) or not resolution.strip():
        raise ValueError("resolution must not be empty.")

    config = settings or get_settings()
    api_symbol = normalize_symbol(symbol)

    base_url = config.wallex_api_base_url.rstrip("/")
    url = f"{base_url}/v1/udf/history"

    params = urlencode(
        {
            "symbol": api_symbol,
            "resolution": resolution,
            "from": start,
            "to": end,
        }
    )

    headers = {
        "Accept": "application/json",
        "User-Agent": "crypto-signals/0.1",
    }

    if config.wallex_api_key:
        headers["X-API-Key"] = config.wallex_api_key

    request = Request(
        f"{url}?{params}",
        headers=headers,
        method="GET",
    )

    try:
        with urlopen(
            request,
            timeout=config.wallex_request_timeout,
        ) as response:
            if response.status != 200:
                raise WallexAPIError(
                    f"Wallex returned HTTP {response.status}."
                )

            raw_body = response.read()

    except HTTPError as exc:
        raise WallexAPIError(
            f"Wallex HTTP error: {exc.code}."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise WallexAPIError(
            f"Could not reach Wallex API: {exc}"
        ) from exc

    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise WallexAPIError(
            "Wallex returned invalid JSON."
        ) from exc

    if not isinstance(payload, dict):
        raise WallexAPIError(
            "Wallex response must be a JSON object."
        )

    if payload.get("s") != "ok":
        raise WallexAPIError(
            f"Wallex response status: {payload.get('s')!r}"
        )

    return payload

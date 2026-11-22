from math import isfinite


def calculate_atr(
    highs: tuple[float, ...],
    lows: tuple[float, ...],
    closes: tuple[float, ...],
    period: int = 14,
) -> tuple[float | None, ...]:
    if isinstance(period, bool) or not isinstance(period, int) or period <= 0:
        raise ValueError("period must be a positive integer")

    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("OHLC lengths do not match")

    if any(
        not isfinite(value)
        for values in (highs, lows, closes)
        for value in values
    ):
        raise ValueError("OHLC values must be finite")

    if any(
        high < low
        for high, low in zip(highs, lows)
    ):
        raise ValueError("high cannot be below low")

    result: list[float | None] = [None] * len(highs)

    if len(highs) < period:
        return tuple(result)

    true_ranges = []

    for index, (high, low, close) in enumerate(zip(highs, lows, closes)):
        if index == 0:
            true_range = high - low
        else:
            true_range = max(
                high - low,
                abs(high - closes[index - 1]),
                abs(low - closes[index - 1]),
            )

        true_ranges.append(true_range)

    atr = sum(true_ranges[:period]) / period
    result[period - 1] = atr

    for index in range(period, len(true_ranges)):
        atr = (
            atr * (period - 1) + true_ranges[index]
        ) / period
        result[index] = atr

    return tuple(result)

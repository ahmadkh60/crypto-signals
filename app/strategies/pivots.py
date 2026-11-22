from dataclasses import dataclass

from app.strategies.base import BarHistory


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float
    confirmed_at: int


def find_confirmed_pivots(
    history: BarHistory,
    left: int = 2,
    right: int = 2,
) -> tuple[tuple[Pivot, ...], tuple[Pivot, ...]]:
    if left <= 0 or right <= 0:
        raise ValueError("left and right must be positive")

    highs = history["high"]
    lows = history["low"]

    if len(highs) != len(lows):
        raise ValueError("high and low lengths do not match")

    pivot_highs = []
    pivot_lows = []

    candidate = history.index - right

    if candidate < left:
        return (), ()

    start = candidate - left
    end = candidate + right + 1

    high_window = highs[start:end]
    low_window = lows[start:end]

    candidate_high = highs[candidate]
    candidate_low = lows[candidate]

    if all(
        candidate_high > value
        for i, value in enumerate(high_window)
        if i != left
    ):
        pivot_highs.append(
            Pivot(
                index=candidate,
                price=candidate_high,
                confirmed_at=history.index,
            )
        )

    if all(
        candidate_low < value
        for i, value in enumerate(low_window)
        if i != left
    ):
        pivot_lows.append(
            Pivot(
                index=candidate,
                price=candidate_low,
                confirmed_at=history.index,
            )
        )

    return tuple(pivot_highs), tuple(pivot_lows)

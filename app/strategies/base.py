from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

SignalAction = Literal["long", "exit", "hold"]


@dataclass(frozen=True)
class Signal:
    action: SignalAction
    reason: str = ""
    stop_distance: float | None = None


@dataclass(frozen=True)
class BarHistory:
    candles: Mapping[str, tuple[object, ...]]
    index: int

    def __getitem__(self, column: str) -> tuple[object, ...]:
        return self.candles[column]

    def __len__(self) -> int:
        return self.index + 1

    @classmethod
    def from_candles(
        cls,
        candles: dict[str, list],
        index: int,
    ) -> "BarHistory":
        if index < 0:
            raise ValueError("index must be non-negative")

        if any(index >= len(values) for values in candles.values()):
            raise ValueError("index is outside candle data")

        visible = {
            name: tuple(values[:index + 1])
            for name, values in candles.items()
        }

        return cls(
            candles=MappingProxyType(visible),
            index=index,
        )


class Strategy(Protocol):
    def on_bar(self, history: BarHistory) -> Signal:
        ...

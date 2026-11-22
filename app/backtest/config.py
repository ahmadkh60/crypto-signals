from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Literal

CostBasis = Literal["real", "hypothetical"]


@dataclass(frozen=True)
class BacktestConfig:
    commission_rate: float
    slippage_rate: float
    cost_basis: CostBasis
    cost_source: str | None = None
    take_profit_r_multiple: float | None = 2.0

    def __post_init__(self):
        multiple = self.take_profit_r_multiple
        if multiple is not None:
            if (
                isinstance(multiple, bool)
                or not isinstance(multiple, Real)
                or not isfinite(multiple)
                or multiple <= 0
            ):
                raise ValueError(
                    "take_profit_r_multiple must be finite and > 0, or None"
                )

        for name in ("commission_rate", "slippage_rate"):
            value = getattr(self, name)

            if isinstance(value, bool) or not isinstance(value, Real):
                raise ValueError(f"{name} must be a real numeric value")

            if not isfinite(value):
                raise ValueError(f"{name} must be finite")

            if not 0 <= value < 1:
                raise ValueError(f"{name} must be in [0, 1)")

        if self.cost_basis not in ("real", "hypothetical"):
            raise ValueError(
                "cost_basis must be 'real' or 'hypothetical'"
            )

        if self.cost_basis == "real":
            if (
                not isinstance(self.cost_source, str)
                or not self.cost_source.strip()
            ):
                raise ValueError(
                    "cost_source is required when cost_basis='real'"
                )

        elif self.cost_source is not None and not isinstance(
            self.cost_source, str
        ):
            raise ValueError("cost_source must be a string or None")

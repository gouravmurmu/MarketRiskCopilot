from dataclasses import dataclass


@dataclass(frozen=True)
class VaRResult:
    """VaR and ES as positive USD loss numbers."""

    var: float
    es: float

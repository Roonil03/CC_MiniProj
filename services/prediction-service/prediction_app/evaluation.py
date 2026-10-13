"""Shared forecasting metrics and observed interval calibration."""

from __future__ import annotations

import math
from statistics import mean


def metrics(actual: list[float], predicted: list[float]) -> dict[str, float | None]:
    if len(actual) != len(predicted) or not actual:
        raise ValueError("equally sized, nonempty arrays required")
    if not all(math.isfinite(v) for v in actual + predicted):
        raise ValueError("metrics require finite values")
    errors = [a - p for a, p in zip(actual, predicted)]
    mae = mean(abs(e) for e in errors)
    rmse = math.sqrt(mean(e * e for e in errors))
    valid_pct = [abs(e / a) for a, e in zip(actual, errors) if abs(a) > 1e-9]
    denominator = sum((a - mean(actual)) ** 2 for a in actual)
    return {"mae": mae, "rmse": rmse,
            "mape": mean(valid_pct) if len(valid_pct) == len(actual) else None,
            "r2": 1 - sum(e * e for e in errors) / denominator if denominator > 0 else None,
            "count": len(actual)}


def residual_radius(actual: list[float], predicted: list[float],
                    coverage: float = 0.9) -> dict[str, float | int]:
    """Finite-sample conformal radius from disjoint validation residuals."""
    if not 0 < coverage < 1 or len(actual) != len(predicted) or not actual:
        raise ValueError("invalid calibration inputs")
    residuals = sorted(abs(a - p) for a, p in zip(actual, predicted))
    rank = min(len(residuals), math.ceil((len(residuals) + 1) * coverage)) - 1
    return {"radius": residuals[rank], "nominal_coverage": coverage,
            "calibration_count": len(residuals)}


def observed_coverage(actual: list[float], predicted: list[float], radius: float) -> float:
    if len(actual) != len(predicted) or not actual or radius < 0:
        raise ValueError("invalid coverage inputs")
    return mean(abs(a - p) <= radius for a, p in zip(actual, predicted))

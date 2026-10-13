"""Comparable one-metric forecasts. Statistical fits are offline baselines."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev


def persistence(history: tuple[float, ...], horizons: tuple[int, ...]) -> list[float]:
    if not history or not horizons:
        raise ValueError("history and horizons are required")
    return [float(history[-1])] * len(horizons)


def statistical(kind: str, history: tuple[float, ...], horizons: tuple[int, ...],
                period_seconds: int = 1) -> list[float]:
    """Refit on past values only; expensive by design and intended offline."""
    if len(history) < 12:
        raise ValueError("statistical baseline needs at least 12 observations")
    steps = tuple(h // period_seconds for h in horizons)
    if any(h <= 0 or h % period_seconds for h in horizons):
        raise ValueError("horizons must align with sampling period")
    if kind == "arima":
        from statsmodels.tsa.arima.model import ARIMA
        fitted = ARIMA(history, order=(1, 0, 0), trend="c").fit()
    elif kind == "ets":
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
        fitted = ExponentialSmoothing(history, trend=None, seasonal=None).fit(optimized=True)
    else:
        raise ValueError("unknown statistical model")
    forecast = fitted.forecast(max(steps))
    return [float(forecast[step - 1]) for step in steps]


@dataclass(frozen=True)
class Scale:
    center: float
    spread: float

    @classmethod
    def fit(cls, histories: list[tuple[float, ...]]) -> "Scale":
        values = [value for history in histories for value in history]
        if not values:
            raise ValueError("empty training histories")
        return cls(mean(values), max(pstdev(values), 1e-6))

    def transform(self, values: tuple[float, ...]) -> list[float]:
        return [(v - self.center) / self.spread for v in values]

    def inverse(self, values: list[float]) -> list[float]:
        return [v * self.spread + self.center for v in values]


def neural_network(kind: str, history_steps: int, outputs: int, hidden: int = 16):
    import torch
    from torch import nn

    class Recurrent(nn.Module):
        def __init__(self, cell):
            super().__init__()
            self.cell = cell(1, hidden, batch_first=True)
            self.head = nn.Linear(hidden, outputs)

        def forward(self, x):
            _, state = self.cell(x.unsqueeze(-1))
            if isinstance(state, tuple):
                state = state[0]
            return self.head(state[-1])

    class TinyTemporal(nn.Module):
        def __init__(self):
            super().__init__()
            self.depthwise = nn.Conv1d(1, 1, kernel_size=5, padding=2, groups=1)
            self.head = nn.Sequential(nn.Linear(history_steps, hidden), nn.ReLU(),
                                      nn.Linear(hidden, outputs))

        def forward(self, x):
            return self.head(torch.relu(self.depthwise(x.unsqueeze(1))).squeeze(1))

    if kind == "lstm":
        return Recurrent(nn.LSTM)
    if kind == "gru":
        return Recurrent(nn.GRU)
    if kind == "temporal":
        return TinyTemporal()
    raise ValueError("unknown neural model")


def fit_neural(kind: str, train, validation, *, history_steps: int,
               horizons: tuple[int, ...], seed: int = 42, epochs: int = 20,
               batch_size: int = 64, learning_rate: float = 0.001, hidden: int = 16):
    import copy
    import torch

    if not train or not validation:
        raise ValueError("training and validation windows are required")
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    scale = Scale.fit([w.history for w in train])
    def tensorize(windows):
        x = torch.tensor([scale.transform(w.history) for w in windows], dtype=torch.float32)
        y = torch.tensor([scale.transform(w.targets) for w in windows], dtype=torch.float32)
        return x, y
    x_train, y_train = tensorize(train)
    x_val, y_val = tensorize(validation)
    network = neural_network(kind, history_steps, len(horizons), hidden)
    optimizer = torch.optim.Adam(network.parameters(), lr=learning_rate)
    best_loss = float("inf")
    best_state = None
    best_epoch = 0
    for epoch in range(epochs):
        network.train()
        generator = torch.Generator().manual_seed(seed + epoch)
        for indices in torch.randperm(len(x_train), generator=generator).split(batch_size):
            optimizer.zero_grad()
            loss = torch.mean((network(x_train[indices]) - y_train[indices]) ** 2)
            if not torch.isfinite(loss):
                raise ValueError("non-finite training loss")
            loss.backward()
            optimizer.step()
        network.eval()
        with torch.no_grad():
            val_loss = float(torch.mean((network(x_val) - y_val) ** 2))
        if val_loss < best_loss - 1e-8:
            best_loss, best_epoch = val_loss, epoch + 1
            best_state = copy.deepcopy(network.state_dict())
        if epoch + 1 - best_epoch >= 5:
            break
    network.load_state_dict(best_state)
    return network, scale, {"validation_mse_scaled": best_loss, "selected_epoch": best_epoch,
                            "parameter_count": sum(p.numel() for p in network.parameters())}


def predict_neural(network, scale: Scale, history: tuple[float, ...]) -> list[float]:
    import torch
    network.eval()
    with torch.no_grad():
        x = torch.tensor([scale.transform(history)], dtype=torch.float32)
        return scale.inverse(network(x)[0].tolist())

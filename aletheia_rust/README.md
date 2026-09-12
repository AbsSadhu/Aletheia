# aletheia_rust

PyO3 native extension providing Aletheia's quant math to the Python backend. Imported directly as `aletheia_rust` — the Python side always goes through `aletheia.core.compute.client.ComputeClient`, never this module directly, so there's a pure-Python fallback if the extension isn't built.

## What's in here

- Options pricing: Black-Scholes + Greeks
- Risk: Monte Carlo VaR and portfolio path simulation (self-contained Xorshift128+ RNG, no external deps)
- Technical indicators: SMA/EMA/RSI/MACD/Bollinger/ATR/VWAP/OBV/Stochastic
- Correlation matrices (full + rolling)
- Backtest metrics: Sharpe/Sortino/Calmar, max drawdown with duration/recovery
- BM25 scoring (used by memory retrieval)
- A thread-safe token-bucket `RateLimiter` PyO3 class
- Regime detection, Fama-French 3-factor regression, options flow metrics (put/call ratio, IV rank/skew), Brier score

## Building

```bash
pip install maturin
maturin develop --release --manifest-path aletheia_rust/Cargo.toml
```

This must succeed before the Python backend's startup preflight check passes (`aletheia/core/main.py` hard-fails if `import aletheia_rust` fails).

## Testing

```bash
cargo test
```

21 inline `#[cfg(test)]` unit tests, covering distribution math, Sharpe/Sortino/Calmar edge cases (empty input, zero variance, no drawdown), tax-drag logic, and Brier score correctness.

## Relationship to `aletheia_engine/`

`../aletheia_engine/` is a separate Axum HTTP sidecar that deliberately re-implements the same math in a standalone process (see its README) — `ComputeClient` prefers the HTTP sidecar when available and falls back to this PyO3 extension, then to pure Python, in that order. A cross-crate regression test in `aletheia_engine` pins both implementations to agree on Sharpe.

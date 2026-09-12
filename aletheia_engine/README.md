# aletheia_engine

Standalone Tokio + Axum HTTP sidecar for the same quant math as `../aletheia_rust/`, exposed over HTTP instead of a Python extension ABI. `ComputeClient` (`aletheia/core/compute/client.py`) calls this first when `compute_engine_enabled` is set, and falls back to the PyO3 extension, then pure Python, if it's unreachable.

Deliberately duplicates `aletheia_rust`'s implementations — both are unit-tested against the same hand-computed values so the two engines are cross-checked, not just individually correct. See `engine_sharpe_agrees_with_aletheia_rust_crate_formula` in `src/main.rs`.

## Endpoints

`/health`, `/compute/indicators`, `/compute/portfolio-metrics`, `/compute/monte-carlo`, `/compute/correlation`, `/compute/regime`, `/compute/factor-model`, `/compute/options-flow`

## Running

```bash
cargo build --release
./target/release/aletheia-engine   # aletheia-engine.exe on Windows
```

Listens on `127.0.0.1:18899` by default. Override with `ALETHEIA_ENGINE_HOST` / `ALETHEIA_ENGINE_PORT` (needed in Docker — bind `0.0.0.0` there, not `127.0.0.1`).

## Testing

```bash
cargo test
```

11 inline `#[cfg(test)]` unit tests covering SMA/EMA/RSI edge cases, Sharpe/Sortino/max-drawdown, and the cross-engine agreement check against `aletheia_rust`. No integration tests hit the Axum routes directly yet — only the underlying helper functions are tested.

# ---------------------------------------------------------------------------
# Stage 1: build the aletheia_rust PyO3 extension into a wheel.
# Must use the SAME Python minor version as the runtime stage below — the
# extension is built against a specific CPython ABI, not abi3.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS rust-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir maturin

WORKDIR /build
COPY aletheia_rust ./aletheia_rust

RUN maturin build --release --manifest-path aletheia_rust/Cargo.toml -o /wheels

# ---------------------------------------------------------------------------
# Stage 2: runtime image — production dependencies only, plus the wheel
# built above. No dev/test tooling ships in this image.
# ---------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml poetry.lock* ./
COPY . .

COPY --from=rust-builder /wheels /wheels

RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Production dependencies only (no dev/test group), then the locally-built
# Rust extension wheel — required by the startup preflight check in
# aletheia/core/main.py, which hard-fails if aletheia_rust isn't importable.
RUN uv pip install -e . \
    && uv pip install /wheels/*.whl

EXPOSE 8899

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8899/api/v1/health || exit 1

CMD ["uvicorn", "aletheia.core.main:app", "--host", "0.0.0.0", "--port", "8899"]

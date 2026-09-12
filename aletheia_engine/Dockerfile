FROM rust:1.82-slim AS builder

WORKDIR /build
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim AS runtime

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/target/release/aletheia-engine /usr/local/bin/aletheia-engine

EXPOSE 18899

HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:18899/health || exit 1

CMD ["aletheia-engine"]

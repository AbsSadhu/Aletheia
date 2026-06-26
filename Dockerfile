FROM python:3.13-slim

WORKDIR /app

# Install system dependencies (needed for compiling Python packages and Rust extensions if necessary)
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependencies definitions
COPY pyproject.toml .
# If we had a uv lock file, we would copy it here. We'll use uv pip install system
# Since we have aletheia_rust compiled locally, we will copy the entire project and run uv sync

COPY . .

# Set up the environment
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install python dependencies
# Note: In production, the rust wheel should be pre-compiled and copied, or maturin build should be run.
# For simplicity in this Dockerfile, we will just install the standard dependencies.
RUN uv pip install -e .[dev]

# Expose the application port
EXPOSE 8899

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost:8899/api/v1/health || exit 1

# Start the application
CMD ["uvicorn", "aletheia.core.main:app", "--host", "0.0.0.0", "--port", "8899"]

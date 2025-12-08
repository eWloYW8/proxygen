FROM python:3.12-slim-bookworm

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Set working directory
WORKDIR /app

# Copy dependency definitions
COPY pyproject.toml uv.lock ./

# Install dependencies
# --frozen ensures we use the exact versions in uv.lock
# --no-install-project skips installing the project itself (useful for caching layers)
RUN uv sync --frozen --no-install-project

# Copy the rest of the application
COPY ./app .
COPY ./main.py .

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# Reset the entrypoint, don't invoke `uv`
ENTRYPOINT []

# Run the application
CMD ["fastapi", "run", "main.py"]
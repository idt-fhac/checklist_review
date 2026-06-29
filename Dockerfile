FROM python:3.14-slim

# Install system dependencies if required (e.g. build-essential, git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:0.11.25 /uv /uvx /bin/

# Set working directory
WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv
# We don't need the dev dependencies for the production image
RUN uv sync --no-dev --locked

# Copy the rest of the application
COPY . .

# Expose the application port
EXPOSE 5555

# Set environment variables for Flask
ENV HOST=0.0.0.0
ENV PORT=5555
ENV PYTHONUNBUFFERED=1

# Run the application
CMD ["uv", "run", "app.py"]

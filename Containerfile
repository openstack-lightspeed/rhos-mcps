# NOTE: UBI9 does not yet provide a Python 3.13 image (only up to 3.12).
# Since pyproject.toml requires python >= 3.13, we use the official Python
# slim image. Switch to a UBI-based image when one becomes available.
FROM python:3.13-slim

WORKDIR /app

# Copy dependency and build files first for better layer caching
COPY pyproject.toml README.md ./

# Copy the source code
COPY src/ src/

# Install the project and its dependencies
RUN pip install --no-cache-dir .

# Use the console_scripts entry point defined in pyproject.toml
ENTRYPOINT ["rhos-ls-mcps"]

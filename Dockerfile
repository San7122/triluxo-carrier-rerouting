# Reproducible environment for the autonomous carrier-rerouting POC + eval.
# Default command runs the offline smoke test (no API key, no network) so a
# reviewer can prove the whole graph + scorer works with a single `docker run`.
FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project
COPY . .

# Deterministic, key-free proof that the graph, retry/escalation paths, and
# scorer all work. Override with e.g. `python -m eval.runner`.
CMD ["python", "-m", "eval.smoke_offline"]

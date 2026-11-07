FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only (no CDK, dev tools, or datagen)
RUN pip install --no-cache-dir \
    fastapi>=0.110.0 \
    "uvicorn[standard]>=0.29.0" \
    boto3>=1.34.0 \
    botocore>=1.34.0 \
    pydantic>=2.5.0 \
    pydantic-settings>=2.2.0 \
    python-dotenv>=1.0.0 \
    pyyaml>=6.0.1 \
    sqlglot>=23.0.0 \
    httpx>=0.27.0 \
    rich>=13.7.0 \
    rdflib>=7.0.0

# Copy application code and config
COPY connector/ connector/
COPY config/ config/
COPY bodhi_sim/ bodhi_sim/

# Health check — Athena warm-up takes ~30s at startup
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["python", "-m", "connector.main"]

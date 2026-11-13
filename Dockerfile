FROM python:3.11-slim

WORKDIR /app

# System deps: supervisor to run both FastAPI + Streamlit in one container
RUN apt-get update && apt-get install -y --no-install-recommends \
    supervisor gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python runtime deps (no CDK/dev/datagen)
RUN pip install --no-cache-dir \
    "fastapi>=0.110.0" \
    "uvicorn[standard]>=0.29.0" \
    "boto3>=1.34.0" \
    "botocore>=1.34.0" \
    "pydantic>=2.5.0" \
    "pydantic-settings>=2.2.0" \
    "python-dotenv>=1.0.0" \
    "pyyaml>=6.0.1" \
    "sqlglot>=23.0.0" \
    "httpx>=0.27.0" \
    "pyarrow>=14.0.0" \
    "pandas>=2.1.0" \
    "streamlit>=1.35.0" \
    "requests>=2.31.0"

# Copy application code
COPY connector/ connector/
COPY config/ config/
COPY app.py .
COPY assets/ assets/
COPY supervisord.conf /etc/supervisor/conf.d/yumburger.conf

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
# Streamlit calls the connector on localhost
ENV CONNECTOR_URL=http://localhost:8000

# App Runner exposes 8501 (Streamlit UI)
# FastAPI runs internally on 8000
EXPOSE 8501

CMD ["/usr/bin/supervisord", "-n", "-c", "/etc/supervisor/supervisord.conf"]

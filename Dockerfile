FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip setuptools wheel

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple || \
    pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

ENV CONFIG_DIR=/app/config

VOLUME ["/app/config", "/app/logs"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import requests; r = requests.get('http://localhost:8000/health'); exit(0 if r.status_code == 200 else 1)"

CMD ["uvicorn", "ai_agent.api.api:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]

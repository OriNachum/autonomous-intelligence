FROM python:3.12-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY static/ static/
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 8080
CMD ["python", "-m", "realtime_api.main"]

#FROM reachy-hearing-thor:r38.2.arm64-sbsa-cu130-24.04
FROM reachy-conversation-full:r38.2.arm64-sbsa-cu130-24.04

WORKDIR /app

# Install system dependencies
RUN apt-get update -qq && \
    apt-get install -y -qq alsa-utils && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements files
COPY gateway_app/requirements.txt /app/gateway_app/requirements.txt
COPY conversation_app/requirements.txt /app/conversation_app/requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r /app/gateway_app/requirements.txt && \
    pip install --no-cache-dir -r /app/conversation_app/requirements.txt

# Copy application code
COPY . /app

# Set Python path
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

CMD ["python3", "-m", "conversation_app.app"]

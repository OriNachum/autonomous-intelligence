FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY demo_cli.py .
COPY run_demo.sh .

# Make scripts executable
RUN chmod +x run_demo.sh

# Create directories for inputs and examples
RUN mkdir -p inputs examples

CMD ["python", "demo_cli.py"]
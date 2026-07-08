FROM python:3.12-slim

WORKDIR /app

# System dependencies for chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies (single source of truth: requirements.txt)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY demo.py .

# Data directory for ChromaDB persistence
RUN mkdir -p /app/data/chroma_db

EXPOSE 5000

ENV FLASK_PORT=5000
ENV PYTHONUNBUFFERED=1

CMD ["python", "src/api/app.py"]

FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/
COPY local-config/ ./local-config/

# Create non-root user and logs directory
RUN adduser --disabled-password --gecos '' appuser
RUN mkdir -p /app/logs
RUN chown -R appuser:appuser /app
USER appuser

# Health check - remove since Railway handles this
# HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
#     CMD python -c "import requests; requests.get('http://localhost:5000/health')" || exit 1

EXPOSE $PORT

# Use gunicorn for production with Railway's PORT
CMD gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 60 app.main:app
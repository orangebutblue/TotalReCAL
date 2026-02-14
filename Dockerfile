FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Copy application
COPY icalarchive icalarchive/

# Create data directory
RUN mkdir -p /data

# Expose ports
EXPOSE 8000 8001

# Run application
CMD ["python", "-m", "icalarchive"]

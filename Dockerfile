FROM python:3.11-slim

WORKDIR /app

# Upgrade pip
RUN pip install --upgrade pip setuptools wheel

# Install dependencies
COPY pyproject.toml .
COPY icalarchive icalarchive/

# Install the application
RUN pip install --no-cache-dir .

# Create data directory
RUN mkdir -p /data

# Expose ports
EXPOSE 8000 8001

# Run application
CMD ["python", "-m", "icalarchive", "/data"]

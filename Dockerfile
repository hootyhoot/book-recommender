# Build stage
FROM python:3.8.18-slim AS builder

# Set working directory
WORKDIR /app

# Install dependencies in a virtual environment
COPY requirements.txt .
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Runtime stage
FROM python:3.8.18-slim

# Install only runtime dependencies if needed (e.g., for compiled libraries)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy only the virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Set environment to use the venv
ENV PATH="/opt/venv/bin:$PATH"

# Run the application
CMD ["python", "app.py"]

# Use Python 3.8.18 Alpine as base
FROM python:3.8.18-alpine3.18 AS builder

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    linux-headers \
    g++ \
    libffi-dev \
    openssl-dev \
    cargo \
    rust

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with no cache
RUN pip install --no-cache-dir --user -r requirements.txt

# Final stage
FROM python:3.8.18-alpine3.18

# Install runtime dependencies only (if needed)
RUN apk add --no-cache libstdc++

# Set working directory
WORKDIR /app

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Update PATH
ENV PATH=/root/.local/bin:$PATH

# Run the application
CMD ["python", "app.py"]

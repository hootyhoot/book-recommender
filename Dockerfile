# Use Python 3.8.18 Alpine as base
FROM python:3.8.18-alpine3.18 AS builder

# Install build dependencies
RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    linux-headers \
    libffi-dev \
    openssl-dev \
    python3-dev \
    py3-pip \
    make \
    cmake \
    build-base \
    cargo \
    rust \
    postgresql-dev \
    libc-dev

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Upgrade pip and install wheel first
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

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

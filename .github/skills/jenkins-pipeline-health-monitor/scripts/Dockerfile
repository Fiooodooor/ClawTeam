# Jenkins Health Agent Docker Image
#
# BUILD FROM REPOSITORY ROOT (not from this folder):
# cd firmware.ethernet.mountevans.mev-tools
# docker build -f scripts/jenkins_health_agent/Dockerfile -t jenkins-health-agent .
#
# OR from jenkins_health_agent folder:
# docker build -f Dockerfile -t jenkins-health-agent ../..

# Use Python Alpine for lightweight image
FROM python:3.11-alpine

# Set proxy environment variables for build
ENV HTTP_PROXY=http://proxy-dmz.intel.com:912
ENV HTTPS_PROXY=http://proxy-dmz.intel.com:912
ENV http_proxy=http://proxy-dmz.intel.com:912
ENV https_proxy=http://proxy-dmz.intel.com:912
ENV NO_PROXY=localhost,127.0.0.1,.intel.com
ENV no_proxy=localhost,127.0.0.1,.intel.com

# Set working directory
WORKDIR /app

# Install system dependencies with proxy support
RUN apk add --no-cache \
    ca-certificates \
    wget \
    && update-ca-certificates

# Copy requirements first for better Docker layer caching  
COPY scripts/jenkins_health_agent/requirements.txt .

# Install Python dependencies with proxy support
RUN pip install --no-cache-dir --proxy $HTTP_PROXY -r requirements.txt

# Copy DB infrastructure (now accessible from repo root context)
COPY CI_Tools/NEW_CI_XML_PARSER/DB_Tools ./DB_Tools/
COPY CI_Tools/NEW_CI_XML_PARSER/common ./common/

# Copy the application
COPY scripts/jenkins_health_agent/pipeline-sanity-checker.py .

# Create non-root user for security
RUN addgroup -g 1001 appuser && \
    adduser -u 1001 -G appuser -s /bin/sh -D appuser

# Create directories for logs and set permissions
RUN mkdir -p /app/logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose Prometheus metrics port
EXPOSE 8002

# Set runtime environment variables
ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_PORT=8002
# Remove proxy settings for runtime - they were only needed for build
ENV HTTP_PROXY=
ENV HTTPS_PROXY=
ENV http_proxy=
ENV https_proxy=
ENV NO_PROXY=
ENV no_proxy=

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8002/metrics || exit 1

# Default command - run in monitoring mode
CMD ["python", "pipeline-sanity-checker.py", "--monitor"]
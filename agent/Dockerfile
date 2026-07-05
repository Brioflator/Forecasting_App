# Standalone agent image — deliberately minimal and independently auditable
# (guide §7.7): non-root, outbound-only, no workspace machinery, three deps.
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "httpx>=0.27" "pyyaml>=6" "jsonpath-ng>=1.6" \
 && useradd --create-home --shell /usr/sbin/nologin agent
COPY src/forecast_agent/agent.py /app/agent.py
USER agent
# agent.config.yaml is mounted read-only by docker-compose.agent.yml
CMD ["python", "/app/agent.py"]

# Build from ~/Projects:
#   docker build -f raphael-notifications/Dockerfile .
FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
COPY raphael-contracts /deps/raphael-contracts
RUN uv pip install --system /deps/raphael-contracts
COPY raphael-notifications/pyproject.toml raphael-notifications/README.md ./
COPY raphael-notifications/src ./src
RUN python3 -c "import re; from pathlib import Path; p=Path('pyproject.toml'); p.write_text(re.sub(r'\n\[tool\.uv\.sources\][^\[]*','\n',p.read_text(),flags=re.S))"
RUN uv pip install --system -e .
ENV RAPHAEL_SERVICE_PORT=8090
EXPOSE 8090
CMD ["uvicorn", "raphael_notifications.app:app", "--host", "0.0.0.0", "--port", "8090"]

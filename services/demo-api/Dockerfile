FROM python:3.12-slim

WORKDIR /srv/demo-api

COPY pyproject.toml /srv/demo-api/pyproject.toml
COPY services/demo-api/demo_api/ /srv/demo-api/demo_api/

RUN pip install --no-cache-dir \
    fastapi>=0.115 \
    "uvicorn[standard]>=0.30" \
    "sqlalchemy[asyncio]>=2.0" \
    asyncpg>=0.29 \
    httpx>=0.27 \
    prometheus-client>=0.20

EXPOSE 8001

CMD ["uvicorn", "demo_api.main:app", "--host", "0.0.0.0", "--port", "8001"]

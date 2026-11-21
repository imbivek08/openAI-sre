FROM python:3.12-slim

WORKDIR /srv/api

COPY pyproject.toml /srv/api/pyproject.toml
COPY agent/ /srv/api/agent/
COPY tools/ /srv/api/tools/
COPY integrations/ /srv/api/integrations/
COPY database/ /srv/api/database/
COPY simulator/ /srv/api/simulator/
COPY api/ /srv/api/api/
COPY examples/ /srv/api/examples/

RUN pip install --no-cache-dir -e .

COPY apps/api/docker-entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

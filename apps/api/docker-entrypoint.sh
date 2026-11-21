#!/bin/sh
set -e

# Run database migrations before starting the API.
alembic -c database/alembic.ini upgrade head

# Start the API.
exec uvicorn api.main:app --host 0.0.0.0 --port 8000

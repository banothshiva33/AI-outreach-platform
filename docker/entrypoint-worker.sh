#!/bin/sh
set -e

echo "Waiting for API/database migrations to complete..."

sleep 10

echo "Starting Celery worker..."

exec celery -A app.workers.celery_app worker --loglevel=info --concurrency=2
#!/usr/bin/env sh
set -eu

APP_DIR=${TESDA_APP_DIR:-/opt/tesda-saas/app}
cd "$APP_DIR"
sudo test -f /opt/tesda-saas/secrets/saas.json
sudo test -f /opt/tesda-saas/secrets/firebase-service-account.json
sudo test -f /opt/tesda-saas/secrets/postgres.env

sudo docker compose -f docker-compose.saas.yml -f docker-compose.server.yml --env-file .env.saas pull || true
sudo docker compose -f docker-compose.saas.yml -f docker-compose.server.yml --env-file .env.saas build web
sudo docker compose -f docker-compose.saas.yml -f docker-compose.server.yml --env-file .env.saas up -d --remove-orphans
sudo docker compose -f docker-compose.saas.yml -f docker-compose.server.yml --env-file .env.saas ps
curl --fail --silent --show-error --retry 12 --retry-connrefused --retry-delay 5 http://127.0.0.1:7080/health/saas

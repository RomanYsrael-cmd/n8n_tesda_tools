#!/usr/bin/env sh
set -eu

APP_DIR=${TESDA_APP_DIR:-/opt/tesda-saas/app}
IMAGE=${TESDA_IMAGE:-ghcr.io/romanysrael-cmd/n8n_tesda_tools:latest}
cd "$APP_DIR"
sudo -n test -f /opt/tesda-saas/secrets/saas.json
sudo -n test -f /opt/tesda-saas/secrets/firebase-service-account.json
sudo -n test -f /opt/tesda-saas/secrets/postgres.env

compose() {
  sudo -n env TESDA_IMAGE="$IMAGE" docker compose -f docker-compose.saas.yml -f docker-compose.server.yml --env-file .env.saas "$@"
}

compose pull web worker
compose up -d --no-build --remove-orphans web worker
compose ps
for container in tesda-saas-web tesda-saas-worker; do
  state=$(sudo -n docker inspect --format '{{.State.Status}}' "$container" 2>/dev/null || true)
  if [ "$state" != running ]; then
    echo "Deployment failed: $container is not running (state: ${state:-missing})" >&2
    exit 1
  fi
done
curl --fail --silent --show-error --retry 12 --retry-connrefused --retry-delay 5 http://127.0.0.1:7080/health/saas

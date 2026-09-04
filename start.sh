#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
command -v docker >/dev/null 2>&1 || { echo "Docker is required. Install and start Docker, then try again."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start it, then try again."; exit 1; }
if [ ! -f .env ]; then
  if [ -f module_builder/.env ]; then
    cp module_builder/.env .env
    echo "Existing local settings were moved to the repository launcher."
  else
    cp .env.example .env
  fi
fi
docker compose up -d --build
echo "TESDA Academic Tools is starting at http://localhost:8080"
case "$(uname -s)" in Darwin) open http://localhost:8080 ;; Linux) command -v xdg-open >/dev/null && xdg-open http://localhost:8080 >/dev/null 2>&1 || true ;; esac

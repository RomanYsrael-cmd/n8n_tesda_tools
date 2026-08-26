#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
command -v docker >/dev/null 2>&1 || { echo "Docker is required. Install and start Docker, then try again."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is not running. Start it, then try again."; exit 1; }
[ -f .env ] || cp .env.example .env
docker compose up -d --build
echo "Module Builder is starting at http://localhost:8080"
case "$(uname -s)" in Darwin) open http://localhost:8080 ;; Linux) command -v xdg-open >/dev/null && xdg-open http://localhost:8080 >/dev/null 2>&1 || true ;; esac

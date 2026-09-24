# SaaS deployment

Cloud mode is deliberately separate from the local launcher. Local clones continue to use `docker-compose.yml`; production uses `docker-compose.saas.yml` plus `docker-compose.server.yml`.

## Production services

- `web`: Firebase-authenticated FastAPI UI on server-local port 7080.
- `worker`: claims durable jobs from PostgreSQL with `FOR UPDATE SKIP LOCKED`.
- PostgreSQL: users, subscriptions, tenant-scoped jobs, progress events, webhook idempotency.
- Cloudflare R2: private syllabi and generated deliverables; downloads use short-lived signed URLs.
- SpaceEmail: completion/failure notifications.
- PayMongo: signed, idempotent webhook ingestion. Pricing and checkout products are configured separately because amounts and entitlements are business decisions.

Cloudflare Tunnel should publish `tools.romanlms.com` to `http://localhost:7080`. No public server port is required.

## Required server files

Place these root-readable files under `/opt/tesda-saas/secrets`:

- `saas.json`
- `firebase-service-account.json`
- `postgres.env` containing `TESDA_DATABASE_URL=...`

Then create `/opt/tesda-saas/app/.env.saas` from `.env.saas.example` and run `sh launcher/scripts/deploy-saas.sh`.

Do not commit any of these secret files.

## GitHub Actions deployment

The repository workflow runs CI for pull requests and pushes. A push to
`main` publishes an immutable commit-tagged image to GHCR and deploys that
exact image to production. Because this server is reachable through a private
Tailscale network, the deployment job runs on a repository-scoped self-hosted
runner installed at `/opt/actions-runner` on the server (label: `tesda-saas`).
No SSH private key is needed in GitHub Actions for this setup.

The runner account must be able to run `sudo -n docker` without an interactive
password and the server must have the production files and secret files listed
above. If the GHCR package is private, the server must already be logged in to
GHCR with permission to pull it. The action runs the same checked deployment
script used for a manual update and verifies both containers plus
`/health/saas` before succeeding.

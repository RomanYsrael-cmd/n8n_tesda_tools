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
exact image to production over SSH. Add these GitHub Actions repository
secrets:

- `TESDA_DEPLOY_HOST`: a public DNS name or IP reachable from GitHub Actions
  (a local SSH alias such as `romanserver-remote` is not sufficient).
- `TESDA_DEPLOY_USER`: the Linux account used for deployment.
- `TESDA_DEPLOY_SSH_KEY`: the private key whose public key is in that account's
  `~/.ssh/authorized_keys`.
- `TESDA_DEPLOY_PORT`: optional SSH port; defaults to `22`.

The deployment account must be able to run `sudo -n docker` without an
interactive password and must have the production files and secret files
listed above. If the GHCR package is private, the server must already be
logged in to GHCR with permission to pull it. The action then runs the same
checked deployment script used for a manual update and verifies
`/health/saas` before succeeding.

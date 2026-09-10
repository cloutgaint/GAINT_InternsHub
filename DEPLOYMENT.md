# Production deployment

The production stack serves the React application and `/api` from one public
origin. Nginx proxies API traffic to FastAPI, while PostgreSQL and the backend
remain on a private Docker network.

## Server requirements

- Linux host with Docker Engine and Docker Compose v2
- A DNS record pointing to the host
- An HTTPS reverse proxy or load balancer in front of port 80
- At least 2 GB RAM and persistent disk space for PostgreSQL and uploaded ZIPs

## Configure

```bash
cp .env.production.example .env.production
```

Replace every `change-me` value. Generate secrets instead of reusing example
passwords:

```bash
openssl rand -hex 32
```

Set all three public URLs to the real HTTPS host. For example:

```env
FRONTEND_URL=https://interns.example.com
PUBLIC_API_URL=https://interns.example.com/api
CERTIFICATE_VERIFY_BASE_URL=https://interns.example.com/api/certificates/verify
```

The bootstrap admin is created only when its email does not already exist.
Demo users are disabled in the production stack. Change the bootstrap password
after the first login and keep `.env.production` outside source control.

## Deploy

```bash
docker compose --env-file .env.production -f compose.production.yml up -d --build
docker compose --env-file .env.production -f compose.production.yml ps
```

Verify readiness through the public HTTPS endpoint:

```bash
curl --fail https://interns.example.com/healthz
curl --fail https://interns.example.com/api/health
```

The API health check includes a database query. Both commands must succeed
before directing users to the application.

## HTTPS and payments

Terminate TLS at a managed load balancer, CDN, Caddy, Traefik, or the host's
existing reverse proxy and forward traffic to `APP_PORT` (port 80 by default).
Do not expose PostgreSQL or backend port 8000 publicly.

For Razorpay, set `PAYMENT_PROVIDER=razorpay`, configure fresh live credentials,
and register this webhook URL:

```text
https://interns.example.com/api/payments/razorpay/webhook
```

Never reuse credentials that appeared in local files, screenshots, chat, or
source control.

## Updates and rollback

Before an update, back up both persistent volumes. Then build and start the new
revision with the same deploy command. Keep the previous image tag/revision so
the application containers can be rolled back without replacing the database
or uploads volumes.

Inspect service logs with:

```bash
docker compose --env-file .env.production -f compose.production.yml logs --tail=200 backend frontend postgres
```

Database schema changes currently use the application's idempotent startup
migrations. Take a database backup before each release.

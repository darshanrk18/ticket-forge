# Web Frontend

Next.js (App Router) UI for TicketForge. The package is `web-frontend` in the
repo root npm workspace.

## Development

From repo root:

```bash
npm run dev --workspace=web-frontend
```

Open http://localhost:3000

Other scripts:

```bash
npm run build --workspace=web-frontend
npm run start --workspace=web-frontend
npm run lint --workspace=web-frontend
```

## Linting and Type Checking

Run these from the repository root:

```bash
npm run lint:web
npm run typecheck:web
```

Run these from `apps/web-frontend`:

```bash
npm run lint
npm run typecheck
```

## API backend configuration

The UI targets the FastAPI backend.
- `NEXT_PUBLIC_API_URL` controls client-side fetch base URL.
- In Cloud Run app-serving mode (`terraform/app_serving.tf`), Terraform injects
  this from the API service URL for the `ticketforge-web` service.

## Production Docker image

`docker/frontend.Dockerfile` builds a standalone Next.js server image (port 8080):

```bash
docker build -f docker/frontend.Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=https://YOUR-API.run.app \
  -t ticketforge-web:local .
```

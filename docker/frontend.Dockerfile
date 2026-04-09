# Next.js production image (standalone output). Build from repo root:
#   docker build -f docker/frontend.Dockerfile -t ticketforge-web .

FROM node:22-bookworm-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
COPY apps/web-frontend/package.json ./apps/web-frontend/
RUN npm ci

FROM node:22-bookworm-slim AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
ARG NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY apps/web-frontend ./apps/web-frontend
WORKDIR /app/apps/web-frontend
RUN npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=8080
ENV HOSTNAME=0.0.0.0

COPY --from=builder /app/apps/web-frontend/.next/standalone ./
COPY --from=builder /app/apps/web-frontend/.next/static ./apps/web-frontend/.next/static
COPY --from=builder /app/apps/web-frontend/public ./apps/web-frontend/public

EXPOSE 8080
CMD ["node", "apps/web-frontend/server.js"]

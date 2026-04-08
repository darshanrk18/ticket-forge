FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web-frontend/package.json apps/web-frontend/package.json

RUN npm ci


FROM node:22-alpine AS builder

WORKDIR /app

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY apps/web-frontend ./apps/web-frontend

RUN npm --workspace apps/web-frontend run build


FROM node:22-alpine AS runtime

WORKDIR /app

ENV NODE_ENV=production \
    PORT=8080 \
    HOSTNAME=0.0.0.0

COPY --from=deps /app/node_modules ./node_modules
COPY package.json package-lock.json ./
COPY --from=builder /app/apps/web-frontend ./apps/web-frontend

EXPOSE 8080

CMD ["npm", "--workspace", "apps/web-frontend", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "8080"]

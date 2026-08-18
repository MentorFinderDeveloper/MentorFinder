# syntax=docker/dockerfile:1

FROM node:22.14.0-bookworm AS frontend-builder

WORKDIR /build/frontend
RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./

ARG PUBLIC_SITE_PATH=/se-projects/mentorfinder
ENV NEXT_PUBLIC_SITE_PATH=${PUBLIC_SITE_PATH}
ENV BACKEND_URL=http://127.0.0.1:8000
RUN pnpm build


FROM node:22.14.0-bookworm AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx python3 python3-venv wget \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/backend/requirements.txt
RUN python3 -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend/ /app/backend/
COPY --from=frontend-builder /build/frontend/.next/standalone /app/frontend/
COPY --from=frontend-builder /build/frontend/.next/static /app/frontend/.next/static/
COPY --from=frontend-builder /build/frontend/public /app/frontend/public/

COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/start.sh /app/deploy/start.sh

RUN mkdir -p /app/data/media /app/static /app/frontend/.next/cache \
    && chown -R 10001:10001 /app \
    && chmod +x /app/deploy/start.sh

EXPOSE 8080

CMD ["/app/deploy/start.sh"]

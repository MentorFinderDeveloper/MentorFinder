# Build the production bundle in an isolated stage so the runtime image stays small.
FROM node:22 AS builder

WORKDIR /build

# Point the frontend proxy at the deployed backend unless overridden at build time.
ENV BACKEND_URL https://backend-mentorfinder.app.spring26a.secoder.net

RUN corepack enable pnpm

COPY package.json pnpm-lock.yaml ./

RUN pnpm config set registry https://registry.npmmirror.com

RUN pnpm install

COPY . .

RUN pnpm build

# Run only the standalone Next.js output in the final image.
FROM node:22 AS runner

WORKDIR /app

# Copy the minimal server bundle, static assets, and public files into the runtime image.
COPY --from=builder /build/.next/standalone .

COPY --from=builder /build/.next/static .next/static

COPY --from=builder /build/public public

ENV PORT 80

EXPOSE 80

CMD ["node", "server.js"]

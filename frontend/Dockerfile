# syntax=docker/dockerfile:1

# ── Build: Node compiles the static bundle ─────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app

# Dependencies first, so this layer is reused until the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ── Serve: nginx only; no Node, node_modules or source in this image ───────
FROM nginx:1.27-alpine

# Run as the image's unprivileged nginx user: move the pid file to /tmp, drop
# the "user" directive (only meaningful as root), and let nginx write the
# rendered config and its temp files.
RUN sed -i -e 's#^pid .*#pid /tmp/nginx.pid;#' -e '/^user /d' /etc/nginx/nginx.conf \
    && rm /etc/nginx/conf.d/default.conf \
    && chown -R nginx:nginx /var/cache/nginx /etc/nginx/conf.d

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html

# Where /api is proxied to. A runtime setting, not a build input: override it
# per environment (Compose, Kubernetes) without rebuilding. See ADR 0002.
ENV BACKEND_URL=http://backend:8000

USER nginx
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["wget", "-q", "-O", "/dev/null", "http://127.0.0.1:8080/healthz"]
# ENTRYPOINT and CMD (exec form) are inherited from nginx:1.27-alpine.

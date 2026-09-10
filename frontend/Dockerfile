FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./

ARG VITE_API_URL=/api
ARG VITE_CERTIFICATE_VERIFY_BASE_URL=/api/certificates/verify
ENV VITE_API_URL=$VITE_API_URL \
    VITE_CERTIFICATE_VERIFY_BASE_URL=$VITE_CERTIFICATE_VERIFY_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz || exit 1

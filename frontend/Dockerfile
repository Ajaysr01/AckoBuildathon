# Build the React/Vite client with a Node version compatible with Vite 8.
FROM node:20.19-alpine AS build

WORKDIR /app

# Keep dependency installation reproducible through the committed lockfile.
COPY package.json package-lock.json ./
RUN npm ci

COPY index.html ./
COPY src ./src

# The browser makes API requests from the host, so use the published API port.
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

# Serve the compiled static app; the API runs in its own container.
FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

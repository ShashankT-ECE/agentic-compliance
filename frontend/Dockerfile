# Agentic Compliance — Frontend Docker image
# Multi-stage build: compile TypeScript + bundle with Vite, serve with Nginx

# ---- Build stage ----
FROM node:22-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# ---- Serve stage ----
FROM nginx:1.27-alpine

# Copy the production build
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config — SPA fallback + API proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]

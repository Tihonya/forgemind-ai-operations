# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install all dependencies (including devDependencies for build)
RUN npm ci

# Copy source code
COPY frontend/ ./

# Build arguments
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Build application
RUN npm run build

# Development stage
FROM node:22-alpine AS development

WORKDIR /app

# Copy package files
COPY frontend/package.json frontend/package-lock.json* ./

# Install all dependencies (including dev)
RUN npm ci

# Copy source code
COPY frontend/ ./

# Expose port
EXPOSE 5173

# Default command
CMD ["npm", "run", "dev"]

# Production stage
FROM nginx:alpine AS production

# Copy built assets from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy nginx configuration
COPY infra/docker/nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost/ || exit 1

# Default command
CMD ["nginx", "-g", "daemon off;"]

# Stage 1: Build
FROM node:20-alpine AS builder
WORKDIR /app

COPY package.json ./
# npm install instead of npm ci — works without package-lock.json
RUN npm install --legacy-peer-deps

COPY . .
RUN npm run build

# Stage 2: Serve via Nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf
EXPOSE 80

FROM node:20-alpine AS builder

WORKDIR /app
ENV CI=1

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

# VITE_* 环境变量会在 build 时嵌入到 bundle；通过 build args 传入
ARG VITE_API_BASE=http://localhost:8000
ARG VITE_CASDOOR_ENDPOINT=https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io
ARG VITE_CASDOOR_CLIENT_ID=d886e62a3d88caa515c1
ARG VITE_CASDOOR_ORG=built-in
ARG VITE_CASDOOR_APP=sales
ARG VITE_CASDOOR_REDIRECT=http://localhost:5173/auth/callback
ARG VITE_TICKET_FRONT=https://gongdan-b5fzbtgteqd5gzfb.eastasia-01.azurewebsites.net

ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_CASDOOR_ENDPOINT=$VITE_CASDOOR_ENDPOINT \
    VITE_CASDOOR_CLIENT_ID=$VITE_CASDOOR_CLIENT_ID \
    VITE_CASDOOR_ORG=$VITE_CASDOOR_ORG \
    VITE_CASDOOR_APP=$VITE_CASDOOR_APP \
    VITE_CASDOOR_REDIRECT=$VITE_CASDOOR_REDIRECT \
    VITE_TICKET_FRONT=$VITE_TICKET_FRONT

RUN npm run build


FROM nginx:1.27-alpine AS runtime

# SPA fallback + /api 反代到后端 api service
RUN cat > /etc/nginx/conf.d/default.conf <<'EOF'
server {
    listen 5173;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /health {
        proxy_pass http://api:8000/health;
    }

    # 静态资源带 hash 可长缓存
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }
}
EOF

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 5173
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:5173/ >/dev/null || exit 1

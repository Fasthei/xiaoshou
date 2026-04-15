# TypeScript SSO Template

把整个目录（或 `casdoor.ts` + `middleware-express.ts` + `roles.ts`）拷到你的 TS 服务（如 `gongdan`），改一下配置即可。

## 1. 安装依赖

```bash
npm i jose axios
# express 场景再装
npm i express
npm i -D @types/express
```

## 2. 环境变量

在 `gongdan` 项目的 `.env` / Container App 环境变量里：

```
CASDOOR_ENDPOINT=https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io
CASDOOR_ORG=xingyun
CASDOOR_APP_NAME=ticket-app
CASDOOR_CLIENT_ID=<from Casdoor console>
CASDOOR_CLIENT_SECRET=<from Casdoor console>
CASDOOR_REDIRECT_URI=https://<ticket-fqdn>/api/auth/callback
AUTH_ENABLED=true
```

## 3. 用法

```ts
import express from 'express';
import { requireAuth, requireRoles } from './auth/middleware-express';
import { Roles } from './auth/roles';
import type { CasdoorConfig } from './auth/casdoor';

const cfg: CasdoorConfig = {
  endpoint: process.env.CASDOOR_ENDPOINT!,
  org: process.env.CASDOOR_ORG!,
  appName: process.env.CASDOOR_APP_NAME!,
  clientId: process.env.CASDOOR_CLIENT_ID!,
  clientSecret: process.env.CASDOOR_CLIENT_SECRET!,
  redirectUri: process.env.CASDOOR_REDIRECT_URI!,
};

const app = express();

app.get('/api/me', requireAuth(cfg), (req, res) => res.json((req as any).user));
app.post('/api/tickets', requireRoles(cfg, Roles.OPS, Roles.ADMIN), (req, res) => { /* ... */ });
```

## 4. Next.js App Router 适配

在 `app/api/*/route.ts` 里：

```ts
import { verifyToken } from '@/auth/casdoor';

export async function GET(req: Request) {
  const auth = req.headers.get('authorization') || '';
  const m = /^Bearer\s+(.+)$/i.exec(auth);
  if (!m) return Response.json({ error: 'unauthorized' }, { status: 401 });
  try {
    const user = await verifyToken(m[1], cfg);
    return Response.json({ user });
  } catch (e) {
    return Response.json({ error: 'invalid token' }, { status: 401 });
  }
}
```

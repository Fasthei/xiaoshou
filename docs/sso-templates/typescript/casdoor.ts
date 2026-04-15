/**
 * Casdoor JWT verification module — TypeScript
 *
 * 目标：工单系统 (gongdan) / 运营中心 / 任何 TS/Node 服务复制此文件即可接入。
 *
 * 依赖：
 *   npm i jose axios
 *
 * 环境变量：
 *   CASDOOR_ENDPOINT         https://casdoor.ashyglacier-8207efd2.eastasia.azurecontainerapps.io
 *   CASDOOR_ORG              xingyun
 *   CASDOOR_APP_NAME         ticket-app        # 每个系统不同
 *   CASDOOR_CLIENT_ID        xxx               # 从 Casdoor 后台拷
 *   CASDOOR_CLIENT_SECRET    xxx
 *   CASDOOR_REDIRECT_URI     https://<app-fqdn>/api/auth/callback
 *   CASDOOR_CERT             (可选) 直接贴 PEM 公钥
 */

import { importSPKI, jwtVerify, type JWTPayload } from 'jose';
import axios from 'axios';

export interface CasdoorConfig {
  endpoint: string;
  org: string;
  appName: string;
  clientId: string;
  clientSecret: string;
  redirectUri: string;
  certPem?: string;
}

export interface CasdoorClaims extends JWTPayload {
  name?: string;
  displayName?: string;
  email?: string;
  owner?: string;
  roles?: Array<string | { name: string }>;
  groups?: string[];
}

export interface CurrentUser {
  sub: string;
  name: string;
  email: string;
  owner: string;
  roles: string[];
  raw: CasdoorClaims;
}

let cachedPem: string | null = null;

async function loadPublicKeyPem(cfg: CasdoorConfig): Promise<string> {
  if (cachedPem) return cachedPem;
  if (cfg.certPem?.includes('BEGIN')) {
    cachedPem = cfg.certPem.replace(/\\n/g, '\n');
    return cachedPem;
  }
  const url = `${cfg.endpoint.replace(/\/$/, '')}/api/get-cert`;
  const res = await axios.get(url, { params: { id: `${cfg.org}/${cfg.appName}` } });
  const cert = res.data?.data?.certificate || res.data?.certificate;
  if (!cert) throw new Error(`empty cert from Casdoor: ${JSON.stringify(res.data)}`);
  cachedPem = cert;
  return cert;
}

export async function verifyToken(token: string, cfg: CasdoorConfig): Promise<CurrentUser> {
  const pem = await loadPublicKeyPem(cfg);
  const key = await importSPKI(pem, 'RS256');

  const { payload } = await jwtVerify(token, key, {
    algorithms: ['RS256'],
    audience: cfg.clientId,
    issuer: cfg.endpoint.replace(/\/$/, ''),
  });

  const claims = payload as CasdoorClaims;
  const rolesField = claims.roles || [];
  const roles = rolesField.map((r) => (typeof r === 'string' ? r : r.name)).filter(Boolean);

  return {
    sub: String(claims.sub || ''),
    name: claims.name || claims.displayName || '',
    email: claims.email || '',
    owner: claims.owner || '',
    roles,
    raw: claims,
  };
}

export async function exchangeCodeForToken(
  code: string,
  cfg: CasdoorConfig
): Promise<Record<string, unknown>> {
  const url = `${cfg.endpoint.replace(/\/$/, '')}/api/login/oauth/access_token`;
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    code,
    client_id: cfg.clientId,
    client_secret: cfg.clientSecret,
    redirect_uri: cfg.redirectUri,
  });
  const res = await axios.post(url, body.toString(), {
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
  });
  return res.data;
}

export function authorizeUrl(cfg: CasdoorConfig, state = 'sso'): string {
  const qs = new URLSearchParams({
    client_id: cfg.clientId,
    response_type: 'code',
    redirect_uri: cfg.redirectUri,
    scope: 'read',
    state,
  });
  return `${cfg.endpoint.replace(/\/$/, '')}/login/oauth/authorize?${qs}`;
}

/**
 * Express / Next.js API route middleware — drop-in auth guard.
 *
 * Usage (Express):
 *   import { requireAuth, requireRoles } from './middleware-express';
 *   app.get('/api/me', requireAuth(cfg), (req, res) => res.json((req as any).user));
 *   app.post('/api/tickets', requireRoles(cfg, 'ops', 'admin'), handler);
 */

import type { Request, Response, NextFunction } from 'express';
import { verifyToken, type CasdoorConfig, type CurrentUser } from './casdoor';

export interface AuthedRequest extends Request {
  user?: CurrentUser;
}

export function requireAuth(cfg: CasdoorConfig) {
  return async (req: AuthedRequest, res: Response, next: NextFunction) => {
    if (process.env.AUTH_ENABLED === 'false') {
      req.user = { sub: 'dev', name: 'dev', email: '', owner: '', roles: ['admin'], raw: {} };
      return next();
    }
    const hdr = req.header('authorization') || '';
    const m = /^Bearer\s+(.+)$/i.exec(hdr);
    if (!m) return res.status(401).json({ error: 'missing bearer token' });
    try {
      req.user = await verifyToken(m[1], cfg);
      return next();
    } catch (e) {
      return res.status(401).json({ error: 'invalid token', detail: (e as Error).message });
    }
  };
}

export function requireRoles(cfg: CasdoorConfig, ...roles: string[]) {
  const guard = requireAuth(cfg);
  return (req: AuthedRequest, res: Response, next: NextFunction) => {
    guard(req, res, (err?: unknown) => {
      if (err) return next(err);
      if (!req.user) return; // already responded
      if (!req.user.roles?.some((r) => roles.includes(r))) {
        return res.status(403).json({ error: `requires one of: ${roles.join(',')}` });
      }
      next();
    });
  };
}

import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { api } from '../api/axios';

export interface CurrentUser {
  sub: string;
  name: string;
  email: string;
  owner: string;
  roles: string[];
}

interface AuthCtx {
  user: CurrentUser | null;
  ready: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const Ctx = createContext<AuthCtx>({} as AuthCtx);

// 仅在开发环境或显式启用时允许 local-dev token 绕过 /api/auth/me
const ALLOW_DEV_BYPASS =
  import.meta.env.DEV || import.meta.env.VITE_ALLOW_DEV_BYPASS === 'true';

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem('xs_token');
    const cached = localStorage.getItem('xs_user');
    if (!token) {
      setReady(true);
      return;
    }
    // Optimistic from cache, then refresh
    if (cached) {
      try { setUser(JSON.parse(cached)); } catch { /* ignore */ }
    }
    // 本地 dev 模式：token 以 'local-dev' 开头时跳过 /api/auth/me，直接用缓存
    if (ALLOW_DEV_BYPASS && token.startsWith('local-dev') && cached) {
      setReady(true);
      return;
    }
    api.get<CurrentUser>('/api/auth/me')
      .then(({ data }) => {
        setUser(data);
        localStorage.setItem('xs_user', JSON.stringify(data));
      })
      .catch(() => {
        localStorage.removeItem('xs_token');
        localStorage.removeItem('xs_user');
        setUser(null);
      })
      .finally(() => setReady(true));
  }, []);

  const login = async (token: string) => {
    localStorage.setItem('xs_token', token);
    // 本地 dev 模式：token 以 'local-dev' 开头时跳过 /api/auth/me，直接用已写入的 xs_user 缓存
    if (ALLOW_DEV_BYPASS && token.startsWith('local-dev')) {
      const cached = localStorage.getItem('xs_user');
      if (cached) {
        try { setUser(JSON.parse(cached)); } catch { /* ignore */ }
      }
      return;
    }
    const { data } = await api.get<CurrentUser>('/api/auth/me');
    localStorage.setItem('xs_user', JSON.stringify(data));
    setUser(data);
  };

  const logout = () => {
    localStorage.removeItem('xs_token');
    localStorage.removeItem('xs_user');
    setUser(null);
    window.location.href = '/login';
  };

  return (
    <Ctx.Provider value={{ user, ready, login, logout, isAuthenticated: !!user }}>
      {children}
    </Ctx.Provider>
  );
}

export const useAuth = () => useContext(Ctx);

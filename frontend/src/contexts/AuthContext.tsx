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

import axios, { AxiosError, InternalAxiosRequestConfig } from 'axios';
import { message } from 'antd';
import { apiBase } from '../config/casdoor';

export const api = axios.create({
  baseURL: apiBase || '/',
  timeout: 30000,
});

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('xs_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (res) => res,
  (err: AxiosError<{ detail?: string }>) => {
    const status = err.response?.status;
    if (status === 401) {
      // token expired / invalid → clear and bounce to login
      localStorage.removeItem('xs_token');
      localStorage.removeItem('xs_user');
      if (!window.location.pathname.startsWith('/login') &&
          !window.location.pathname.startsWith('/auth/callback')) {
        window.location.href = '/login';
      }
    } else if (status && status >= 500) {
      // 5xx: upstream / gateway issues (e.g. 502 from /api/bridge/* when
      // cloudcost 云管 is unreachable). Don't toast — let the component
      // render its own friendly error state (Result / Empty) so the user
      // sees business context instead of a terse global message.
    } else if (status && status >= 400) {
      const raw = err.response?.data?.detail;
      const detail = typeof raw === 'string'
        ? raw
        : raw != null
          ? JSON.stringify(raw)
          : err.message;
      message.error(`${status}: ${detail}`);
    }
    return Promise.reject(err);
  },
);

/**
 * 读取当前登录用户的角色列表。来源: localStorage.xs_user.roles
 * 用于前端菜单过滤 / 守卫判定。返回空数组表示未登录或未设置角色。
 */
export function getCurrentRoles(): string[] {
  try {
    return (JSON.parse(localStorage.getItem('xs_user') || '{}')?.roles || []) as string[];
  } catch {
    return [];
  }
}

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
    } else if (status && status >= 400) {
      const detail = err.response?.data?.detail || err.message;
      message.error(`${status}: ${detail}`);
    }
    return Promise.reject(err);
  },
);

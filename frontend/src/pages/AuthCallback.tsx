import { useEffect, useRef, useState } from 'react';
import { Card, Alert, Spin, Button, Typography } from 'antd';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { api } from '../api/axios';
import { useAuth } from '../contexts/AuthContext';

const { Text } = Typography;

export default function AuthCallback() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const { login } = useAuth();
  const [err, setErr] = useState('');
  const ran = useRef(false);

  useEffect(() => {
    if (ran.current) return;
    ran.current = true;

    const code = params.get('code');
    const state = params.get('state');
    const oauthErr = params.get('error');

    if (oauthErr) { setErr(params.get('error_description') || oauthErr); return; }
    if (!code) { setErr('缺少 code 参数'); return; }

    const saved = sessionStorage.getItem('casdoor_state');
    if (saved && state && saved !== state) {
      setErr('state 校验失败，可能遭遇 CSRF');
      return;
    }

    (async () => {
      try {
        // Backend /api/auth/callback exchanges code → token_resp
        const { data } = await api.get('/api/auth/callback', { params: { code, state: state || '' } });
        const token: string | undefined = data.access_token || data.id_token;
        if (!token) throw new Error('响应未包含 access_token');
        await login(token);
        sessionStorage.removeItem('casdoor_state');
        nav('/customers', { replace: true });
      } catch (e: any) {
        setErr(e.response?.data?.detail || e.message || '登录失败');
      }
    })();
  }, [params, nav, login]);

  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
      <Card style={{ width: 480 }}>
        {err ? (
          <>
            <Alert type="error" showIcon message="登录失败" description={err} />
            <div style={{ marginTop: 16, textAlign: 'center' }}>
              <Button type="primary" onClick={() => (window.location.href = '/login')}>
                返回登录
              </Button>
            </div>
          </>
        ) : (
          <div style={{ textAlign: 'center' }}>
            <Spin size="large" />
            <div style={{ marginTop: 16 }}>
              <Text type="secondary">正在完成登录…</Text>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

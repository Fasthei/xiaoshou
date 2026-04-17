import { Navigate } from 'react-router-dom';
import { Result } from 'antd';

interface Props {
  allowed: string[];
  children: React.ReactNode;
}

/**
 * RoleGuard — 基于 localStorage.xs_user.roles 的路由守卫。
 *
 * 语义:
 *   - 未登录 (无 xs_user): 跳 /login
 *   - user 角色命中 allowed: 放行
 *   - user 有 admin 或 root 角色 (系统超管): 即便不在 allowed 里也放行（降级通道，避免 Casdoor role 未同步时锁死）
 *   - 其余: 显示 403
 *
 * 未来 Casdoor 同步 'sales-manager' / 'sales' 两种业务 role 后，该守卫自然生效。
 */
export default function RoleGuard({ allowed, children }: Props) {
  const userStr = localStorage.getItem('xs_user');
  if (!userStr) return <Navigate to="/login" replace />;

  let roles: string[] = [];
  try {
    roles = (JSON.parse(userStr)?.roles || []) as string[];
  } catch {
    roles = [];
  }

  const ok = roles.some((r) => allowed.includes(r));
  const isAdmin = roles.includes('admin') || roles.includes('root');
  if (!ok && !isAdmin) {
    return <Result status="403" title="403 禁止访问" subTitle="当前角色无权查看此页面" />;
  }
  return <>{children}</>;
}

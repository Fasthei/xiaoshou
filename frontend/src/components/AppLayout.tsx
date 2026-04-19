import { useEffect, useState } from 'react';
import {
  Layout, Menu, Avatar, Dropdown, Typography, Tag, Space, Tooltip, Button, theme,
} from 'antd';
import {
  TeamOutlined, InboxOutlined, AppstoreOutlined, DashboardOutlined,
  LogoutOutlined, UserOutlined,
  SearchOutlined, BulbOutlined, BulbFilled,
  AlertOutlined, DollarOutlined, FundProjectionScreenOutlined,
  RocketOutlined, ScheduleOutlined,
} from '@ant-design/icons';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';
import { useThemeMode } from '../contexts/ThemeContext';
import { getCurrentRoles } from '../api/axios';
import CommandPalette from './CommandPalette';

const { Header, Sider, Content } = Layout;

// roles 为 undefined 表示所有 authenticated user 可见。
// 超管 (admin / root) 永远可见全部。
type MenuEntry = {
  key: string;
  icon: React.ReactNode;
  label: React.ReactNode;
  roles?: string[];
  hideForRoles?: string[];
};

const ALL_MENU_ITEMS: MenuEntry[] = [
  { key: '/home',        icon: <RocketOutlined />,     label: <Link to="/home">我的工作台</Link>, hideForRoles: ['sales-manager'] },
  { key: '/dashboard',   icon: <DashboardOutlined />,  label: <Link to="/dashboard">总览</Link>, hideForRoles: ['sales'] },
  { key: '/manager',     icon: <FundProjectionScreenOutlined />, label: <Link to="/manager">主管中心</Link>, roles: ['sales-manager'] },
  { key: '/follow-ups',  icon: <ScheduleOutlined />,   label: <Link to="/follow-ups">跟进</Link> },
  { key: '/customers',   icon: <TeamOutlined />,       label: <Link to="/customers">客户管理</Link> },
  { key: '/resources',   icon: <InboxOutlined />,      label: <Link to="/resources">货源看板</Link> },
  { key: '/allocations', icon: <AppstoreOutlined />,   label: <Link to="/allocations">订单管理</Link> },
  { key: '/alerts',      icon: <AlertOutlined />,      label: <Link to="/alerts">预警中心</Link>, hideForRoles: ['sales-manager'] },
  { key: '/bills',       icon: <DollarOutlined />,     label: <Link to="/bills">账单中心</Link>, roles: ['sales', 'sales-manager'] },
  // 报表 BI 不再作为独立菜单，已作为账单中心内的一个 Tab（仅 sales-manager/admin 可见）。
];

function filterMenuByRoles(roles: string[]): MenuEntry[] {
  const isAdmin = roles.includes('admin') || roles.includes('root');
  return ALL_MENU_ITEMS.filter((it) => {
    // hideForRoles 是 "角色黑名单"：即使账号也挂 admin，只要同时挂了被黑的角色就隐藏。
    // 这样 admin+sales-manager 混合账号看到的菜单，和纯 sales-manager 一致；
    // 纯 admin（无 sales-manager/sales 角色）不会命中 hideForRoles，仍然看得到
    // /home /alerts 等给普通销售用的菜单。
    if (it.hideForRoles?.some((r) => roles.includes(r))) return false;
    if (!it.roles) return true;
    if (isAdmin) return true;
    return it.roles.some((r) => roles.includes(r));
  });
}

export default function AppLayout() {
  const { user, logout } = useAuth();
  const { mode, toggle } = useThemeMode();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [cmdOpen, setCmdOpen] = useState(false);
  const { token } = theme.useToken();
  const menuItems = filterMenuByRoles(getCurrentRoles());

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdOpen(true);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible collapsed={collapsed} onCollapse={setCollapsed}
        theme={mode === 'dark' ? 'dark' : 'light'}
        width={220}
        style={{ borderRight: `1px solid ${token.colorBorderSecondary}` }}
      >
        <div style={{
          height: 56, display: 'flex', alignItems: 'center',
          justifyContent: 'center', gap: 8,
        }}>
          <div style={{
            width: 28, height: 28,
            borderRadius: 4,
            background: '#0078D4',
            display: 'grid', placeItems: 'center', fontSize: 16,
          }}>🛒</div>
          {!collapsed && (
            <Typography.Text strong style={{ fontSize: 15, color: mode === 'dark' ? '#fff' : undefined }}>
              销售系统
            </Typography.Text>
          )}
        </div>
        <Menu
          mode="inline"
          theme={mode === 'dark' ? 'dark' : 'light'}
          selectedKeys={[loc.pathname]}
          items={menuItems}
        />
      </Sider>
      <Layout>
        <Header style={{
          background: token.colorBgContainer,
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}>
          <Tooltip title="全局搜索 (⌘/Ctrl + K)">
            <Button
              icon={<SearchOutlined />}
              onClick={() => setCmdOpen(true)}
              style={{
                borderRadius: 999, paddingInline: 16,
                color: token.colorTextSecondary,
                background: token.colorBgElevated,
              }}
            >
              搜索客户 / 跳转 …
              <Tag style={{ marginLeft: 8, fontFamily: 'monospace' }}>⌘K</Tag>
            </Button>
          </Tooltip>
          <Space size={12}>
            <Tooltip title={mode === 'dark' ? '切到亮色' : '切到暗色'}>
              <Button
                type="text"
                icon={mode === 'dark' ? <BulbFilled /> : <BulbOutlined />}
                onClick={toggle}
              />
            </Tooltip>
            <Dropdown menu={{
              items: [
                { key: 'info', label: <span><UserOutlined /> {user?.name || '-'} ({user?.owner})</span>, disabled: true },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
              ],
            }}>
              <Space style={{ cursor: 'pointer' }}>
                <Avatar style={{ background: '#0078D4' }}>
                  {user?.name?.[0]?.toUpperCase() || 'U'}
                </Avatar>
                <span>{user?.name || '未知'}</span>
                {user?.roles?.length ? (
                  <>{user.roles.slice(0, 2).map((r) => <Tag color="blue" key={r}>{r}</Tag>)}</>
                ) : null}
              </Space>
            </Dropdown>
          </Space>
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>

      <CommandPalette open={cmdOpen} onClose={() => setCmdOpen(false)} />
    </Layout>
  );
}

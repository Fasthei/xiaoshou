import { useState } from 'react';
import { Layout, Menu, Avatar, Dropdown, Typography, Tag, Space, theme } from 'antd';
import {
  TeamOutlined, InboxOutlined, AppstoreOutlined,
  LineChartOutlined, LogoutOutlined, UserOutlined,
} from '@ant-design/icons';
import { Link, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/customers',   icon: <TeamOutlined />,      label: <Link to="/customers">客户管理</Link> },
  { key: '/resources',   icon: <InboxOutlined />,     label: <Link to="/resources">货源管理</Link> },
  { key: '/allocations', icon: <AppstoreOutlined />,  label: <Link to="/allocations">分配管理</Link> },
  { key: '/usage',       icon: <LineChartOutlined />, label: <Link to="/usage">用量查询</Link> },
];

export default function AppLayout() {
  const { user, logout } = useAuth();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const { token } = theme.useToken();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        width={220}
        style={{ borderRight: `1px solid ${token.colorBorderSecondary}` }}
      >
        <div style={{ height: 56, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Typography.Text strong style={{ fontSize: 16 }}>
            🛒 {collapsed ? '' : '销售系统'}
          </Typography.Text>
        </div>
        <Menu mode="inline" selectedKeys={[loc.pathname]} items={menuItems} />
      </Sider>
      <Layout>
        <Header
          style={{
            background: token.colorBgContainer,
            padding: '0 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: `1px solid ${token.colorBorderSecondary}`,
          }}
        >
          <Typography.Title level={4} style={{ margin: 0 }}>
            {menuItems.find((m) => m.key === loc.pathname)?.label ? '' : ''}
          </Typography.Title>
          <Dropdown
            menu={{
              items: [
                { key: 'info', label: <span><UserOutlined /> {user?.name || '-'} ({user?.owner})</span>, disabled: true },
                { type: 'divider' },
                { key: 'logout', icon: <LogoutOutlined />, label: '退出登录', onClick: logout },
              ],
            }}
          >
            <Space style={{ cursor: 'pointer' }}>
              <Avatar icon={<UserOutlined />} />
              <span>{user?.name || '未知'}</span>
              {user?.roles?.length ? (
                <>
                  {user.roles.slice(0, 2).map((r) => <Tag color="blue" key={r}>{r}</Tag>)}
                </>
              ) : null}
            </Space>
          </Dropdown>
        </Header>
        <Content style={{ padding: 24 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}

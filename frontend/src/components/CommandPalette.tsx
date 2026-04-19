import { useEffect, useMemo, useRef, useState } from 'react';
import { Modal, Input, List, Tag, Space, Typography, Empty } from 'antd';
import {
  SearchOutlined, TeamOutlined, InboxOutlined, AppstoreOutlined,
  DashboardOutlined, LineChartOutlined, SyncOutlined, LogoutOutlined,
  FunnelPlotOutlined, FundProjectionScreenOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api } from '../api/axios';
import { useAuth } from '../contexts/AuthContext';

const { Text } = Typography;

interface Entry {
  key: string;
  icon: JSX.Element;
  title: string;
  hint?: string;
  tag?: string;
  action: () => void;
}

export default function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<Entry[]>([]);
  const [focus, setFocus] = useState(0);
  const nav = useNavigate();
  const { logout } = useAuth();
  const debounce = useRef<number | null>(null);

  const staticEntries: Entry[] = useMemo(() => [
    { key: 'nav:dashboard',   icon: <DashboardOutlined />,  title: '总览',    hint: '回到仪表盘',  action: () => nav('/dashboard') },
    { key: 'nav:customers',   icon: <TeamOutlined />,       title: '客户管理', hint: '客户主档',    action: () => nav('/customers') },
    { key: 'nav:resources',   icon: <InboxOutlined />,      title: '货源看板', hint: '货源池',      action: () => nav('/resources') },
    { key: 'nav:allocations', icon: <AppstoreOutlined />,   title: '订单管理', hint: '毛利 / 状态', action: () => nav('/allocations') },
    { key: 'nav:usage',       icon: <LineChartOutlined />,  title: '用量查询', hint: '按客户查用量', action: () => nav('/usage') },
    { key: 'nav:manager-center', icon: <FundProjectionScreenOutlined />, title: '主管中心', hint: '销售团队 / 审批中心', action: () => nav('/manager') },
    { key: 'nav:home-funnel', icon: <FunnelPlotOutlined />, title: '切到漏斗',   hint: '销售漏斗概览',  action: () => nav('/home?view=funnel') },
    { key: 'nav:home-kanban', icon: <AppstoreOutlined />,   title: '切到 Kanban', hint: '客户看板视图', action: () => nav('/home?view=kanban') },
    { key: 'act:sync',        icon: <SyncOutlined />,       title: '从工单同步客户', tag: '动作',
      action: async () => {
        try { await api.post('/api/sync/customers/from-ticket'); } finally { /* noop */ }
      },
    },
    { key: 'act:logout',      icon: <LogoutOutlined />,     title: '退出登录', tag: '动作', action: () => logout() },
  ], [nav, logout]);

  // Live search customers
  useEffect(() => {
    if (!open) return;
    if (debounce.current) window.clearTimeout(debounce.current);
    const query = q.trim();
    const lowered = query.toLowerCase();
    const filteredStatic = staticEntries.filter((e) =>
      !query || e.title.toLowerCase().includes(lowered) || (e.hint || '').toLowerCase().includes(lowered),
    );

    if (!query) {
      setResults(filteredStatic);
      setFocus(0);
      return;
    }

    debounce.current = window.setTimeout(async () => {
      try {
        const { data } = await api.get('/api/customers', { params: { keyword: query, page_size: 6 } });
        const custs: Entry[] = (data.items || []).map((c: any) => ({
          key: `c:${c.id}`,
          icon: <TeamOutlined />,
          title: c.customer_name,
          hint: c.customer_code,
          tag: '客户',
          action: () => nav(`/customers?keyword=${encodeURIComponent(c.customer_code)}`),
        }));
        setResults([...filteredStatic, ...custs]);
        setFocus(0);
      } catch {
        setResults(filteredStatic);
      }
    }, 180) as unknown as number;
  }, [q, open, staticEntries, nav]);

  // Keyboard
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') { e.preventDefault(); setFocus((f) => Math.min(f + 1, results.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setFocus((f) => Math.max(f - 1, 0)); }
      else if (e.key === 'Enter') {
        e.preventDefault();
        const r = results[focus]; if (r) { r.action(); onClose(); }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, results, focus, onClose]);

  // Reset on close
  useEffect(() => { if (!open) { setQ(''); setFocus(0); } }, [open]);

  return (
    <Modal
      open={open} onCancel={onClose} footer={null} closable={false}
      width={620} style={{ top: 80 }} destroyOnClose maskClosable
      styles={{ body: { padding: 0 }, content: { borderRadius: 16, overflow: 'hidden' } }}
    >
      <Input
        autoFocus prefix={<SearchOutlined />} placeholder="搜索客户 / 跳转页面 / 执行动作…"
        value={q} onChange={(e) => setQ(e.target.value)}
        size="large"
        style={{ border: 'none', fontSize: 16, padding: '16px 18px' }}
      />
      <div className="cmd-list" style={{ maxHeight: 360, overflowY: 'auto', borderTop: '1px solid #eee' }}>
        {results.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="无匹配" style={{ padding: 32 }} />
        ) : (
          <List
            dataSource={results}
            renderItem={(r, i) => (
              <List.Item
                onClick={() => { r.action(); onClose(); }}
                onMouseEnter={() => setFocus(i)}
                style={{
                  padding: '10px 18px', cursor: 'pointer',
                  background: i === focus ? '#DEECF9' : undefined,
                  borderLeft: i === focus ? '3px solid #0078D4' : '3px solid transparent',
                }}
              >
                <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <Text style={{ fontSize: 16 }}>{r.icon}</Text>
                    <div>
                      <div>{r.title}</div>
                      {r.hint ? <Text type="secondary" style={{ fontSize: 12 }}>{r.hint}</Text> : null}
                    </div>
                  </Space>
                  {r.tag ? <Tag color="blue">{r.tag}</Tag> : null}
                </Space>
              </List.Item>
            )}
          />
        )}
      </div>
      <div style={{ padding: '8px 18px', borderTop: '1px solid #eee', background: '#fafafa' }}>
        <Space size={16}>
          <Text type="secondary" style={{ fontSize: 12 }}>↑↓ 移动</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>↵ 选中</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>ESC 关闭</Text>
        </Space>
      </div>
    </Modal>
  );
}

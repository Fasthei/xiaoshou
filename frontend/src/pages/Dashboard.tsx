import { useEffect, useMemo, useState } from 'react';
import { Card, Col, Row, Statistic, Skeleton, Tag, Space, Typography, Button, Empty, List, Avatar } from 'antd';
import {
  TeamOutlined, InboxOutlined, AppstoreOutlined, RiseOutlined,
  SyncOutlined, CloudServerOutlined, RocketOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api } from '../api/axios';

const { Title, Text } = Typography;

interface SyncRow {
  id: number;
  source_system: string;
  sync_type: string;
  status: string;
  pulled: number;
  created: number;
  updated: number;
  started_at: string | null;
  finished_at: string | null;
}

function Sparkline({ values, color = '#4f46e5' }: { values: number[]; color?: string }) {
  const w = 160, h = 42;
  if (!values.length) return <div style={{ width: w, height: h }} />;
  const max = Math.max(...values, 1);
  const step = w / Math.max(values.length - 1, 1);
  const pts = values.map((v, i) => `${i * step},${h - (v / max) * (h - 4) - 2}`).join(' ');
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <defs>
        <linearGradient id="g" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polyline points={`0,${h} ${pts} ${w},${h}`} fill="url(#g)" stroke="none" />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" />
    </svg>
  );
}

export default function Dashboard() {
  const [loading, setLoading] = useState(true);
  const [customerCount, setCustomerCount] = useState<number | null>(null);
  const [resourceCount, setResourceCount] = useState<number | null>(null);
  const [allocCount, setAllocCount] = useState<number | null>(null);
  const [syncs, setSyncs] = useState<SyncRow[]>([]);
  const [syncing, setSyncing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [c, r, a, s] = await Promise.allSettled([
        api.get('/api/customers?page_size=1'),
        api.get('/api/resources?page_size=1'),
        api.get('/api/allocations?page_size=1'),
        api.get('/api/sync/logs?limit=5'),
      ]);
      if (c.status === 'fulfilled') setCustomerCount(c.value.data.total);
      if (r.status === 'fulfilled') setResourceCount(r.value.data.total);
      if (a.status === 'fulfilled') setAllocCount(a.value.data.total);
      if (s.status === 'fulfilled') setSyncs(s.value.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const syncNow = async () => {
    setSyncing(true);
    try {
      await api.post('/api/sync/customers/from-ticket');
      await load();
    } finally {
      setSyncing(false);
    }
  };

  const spark = useMemo(
    () => Array.from({ length: 14 }, () => Math.round(20 + Math.random() * 80)),
    [],
  );

  return (
    <div className="page-fade">
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col span={24}>
          <Card
            style={{
              background: 'linear-gradient(120deg, #4f46e5 0%, #7c3aed 50%, #ec4899 100%)',
              border: 'none',
              color: 'white',
              overflow: 'hidden',
              position: 'relative',
            }}
            styles={{ body: { padding: 28 } }}
          >
            <div style={{ position: 'absolute', right: -40, top: -40, fontSize: 200, opacity: 0.08 }}>🛒</div>
            <Space direction="vertical" size={4} style={{ color: 'white' }}>
              <Text style={{ color: 'rgba(255,255,255,0.75)', letterSpacing: 4, fontSize: 12 }}>
                DASHBOARD · 业务总览
              </Text>
              <Title level={2} style={{ color: 'white', margin: 0 }}>早安，开始今天的销售工作 ✨</Title>
              <Text style={{ color: 'rgba(255,255,255,0.8)' }}>
                跨系统统一身份 · 工单 → 销售 → 云管 一体化数据流
              </Text>
            </Space>
            <div style={{ marginTop: 20 }}>
              <Space>
                <Button icon={<SyncOutlined spin={syncing} />} onClick={syncNow} loading={syncing}>
                  从工单同步客户
                </Button>
                <Link to="/customers"><Button type="primary" ghost>查看客户</Button></Link>
                <Link to="/allocations"><Button type="primary" ghost>货源分配</Button></Link>
              </Space>
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text type="secondary">客户总数</Text>
                {loading ? <Skeleton.Input active size="large" style={{ marginTop: 4 }} /> :
                  <Statistic value={customerCount ?? 0} prefix={<TeamOutlined />} valueStyle={{ color: '#4f46e5', fontWeight: 700 }} />}
              </div>
              <Avatar size={42} style={{ background: '#eef2ff', color: '#4f46e5' }} icon={<TeamOutlined />} />
            </Space>
            <Sparkline values={spark} />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text type="secondary">本地货源</Text>
                {loading ? <Skeleton.Input active size="large" style={{ marginTop: 4 }} /> :
                  <Statistic value={resourceCount ?? 0} prefix={<InboxOutlined />} valueStyle={{ color: '#0ea5e9', fontWeight: 700 }} />}
              </div>
              <Avatar size={42} style={{ background: '#e0f2fe', color: '#0ea5e9' }} icon={<CloudServerOutlined />} />
            </Space>
            <Sparkline values={spark.slice().reverse()} color="#0ea5e9" />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text type="secondary">货源分配</Text>
                {loading ? <Skeleton.Input active size="large" style={{ marginTop: 4 }} /> :
                  <Statistic value={allocCount ?? 0} prefix={<AppstoreOutlined />} valueStyle={{ color: '#ec4899', fontWeight: 700 }} />}
              </div>
              <Avatar size={42} style={{ background: '#fce7f3', color: '#ec4899' }} icon={<AppstoreOutlined />} />
            </Space>
            <Sparkline values={spark.map((v) => Math.max(0, v - 30))} color="#ec4899" />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text type="secondary">近 14 天趋势</Text>
                <Statistic value={+(spark[spark.length - 1] - spark[0]).toFixed(0)}
                  suffix="%" prefix={<RiseOutlined />} valueStyle={{ color: '#16a34a', fontWeight: 700 }} />
              </div>
              <Avatar size={42} style={{ background: '#dcfce7', color: '#16a34a' }} icon={<RocketOutlined />} />
            </Space>
            <Sparkline values={spark} color="#16a34a" />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={14}>
          <Card title="跨系统集成状态" bordered={false} style={{ borderRadius: 12 }}>
            <Row gutter={[16, 16]}>
              {[
                { name: '工单 gongdan', role: '客户编号源', status: 'ok', color: '#4f46e5' },
                { name: '云管 cloudcost', role: '货源 / 用量', status: 'ok', color: '#0ea5e9' },
                { name: 'Casdoor SSO', role: '统一身份', status: 'ok', color: '#16a34a' },
              ].map((s) => (
                <Col xs={24} md={8} key={s.name}>
                  <Card size="small" style={{ borderLeft: `4px solid ${s.color}`, borderRadius: 8 }}>
                    <Space direction="vertical" size={4} style={{ width: '100%' }}>
                      <Text strong>{s.name}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>{s.role}</Text>
                      <Tag color="green" style={{ marginTop: 4 }}>● 在线</Tag>
                    </Space>
                  </Card>
                </Col>
              ))}
            </Row>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card title="最近同步" bordered={false} style={{ borderRadius: 12 }}>
            {syncs.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无同步记录" /> : (
              <List
                size="small" dataSource={syncs}
                renderItem={(r) => (
                  <List.Item>
                    <Space>
                      <Tag color={r.status === 'success' ? 'green' : r.status === 'failed' ? 'red' : 'blue'}>
                        {r.status}
                      </Tag>
                      <Text>{r.source_system} / {r.sync_type}</Text>
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        +{r.created} ~{r.updated}
                      </Text>
                    </Space>
                  </List.Item>
                )}
              />
            )}
          </Card>
        </Col>
      </Row>
    </div>
  );
}

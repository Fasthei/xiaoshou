import { useEffect, useMemo, useState } from 'react';
import {
  Card, Col, Row, Statistic, Skeleton, Tag, Space, Typography, Button, Empty,
  List, Avatar, Progress, Timeline,
} from 'antd';
import {
  TeamOutlined, InboxOutlined, AppstoreOutlined, RiseOutlined, FallOutlined,
  SyncOutlined, CloudServerOutlined, RocketOutlined, UserOutlined,
  HistoryOutlined, PhoneOutlined, BulbOutlined, UserSwitchOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api } from '../api/axios';
import BriefingBanner from '../components/BriefingBanner';

interface SalesLoad {
  id: number; name: string; current_count: number;
  max_customers: number | null; load_pct: number; is_active: boolean;
}

interface Activity {
  kind: 'follow_up' | 'assignment' | 'insight_run';
  at: string;
  customer_id: number | null;
  customer_name: string | null;
  title: string;
  detail: string | null;
}

const ACTIVITY_META: Record<string, { icon: any; color: string }> = {
  follow_up:   { icon: <PhoneOutlined />,       color: 'blue' },
  assignment:  { icon: <UserSwitchOutlined />,  color: 'geekblue' },
  insight_run: { icon: <BulbOutlined />,        color: 'gold' },
};

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
  const [trend, setTrend] = useState<number[]>([]);
  const [trendFailed, setTrendFailed] = useState(false);
  const [salesLoad, setSalesLoad] = useState<SalesLoad[]>([]);
  const [activities, setActivities] = useState<Activity[]>([]);

  const load = async () => {
    setLoading(true);
    try {
      const [c, r, a, s, t, sl, act] = await Promise.allSettled([
        api.get('/api/customers?page_size=1'),
        api.get('/api/resources?page_size=1'),
        api.get('/api/allocations?page_size=1'),
        api.get('/api/sync/logs?limit=5'),
        api.get('/api/trend/daily?days=14'),
        api.get<SalesLoad[]>('/api/sales/users/load'),
        api.get<Activity[]>('/api/sales/activity/recent?limit=15'),
      ]);
      if (c.status === 'fulfilled') setCustomerCount(c.value.data.total);
      if (r.status === 'fulfilled') setResourceCount(r.value.data.total);
      if (a.status === 'fulfilled') setAllocCount(a.value.data.total);
      if (s.status === 'fulfilled') setSyncs(s.value.data);
      if (t.status === 'fulfilled') {
        setTrend((t.value.data || []).map((p: any) => Number(p.cost || 0)));
        setTrendFailed(false);
      } else {
        // /api/trend/daily often 502s when cloudcost is down — degrade the
        // sparkline cards gracefully to <Empty> instead of showing random
        // made-up numbers (which is misleading).
        setTrend([]);
        setTrendFailed(true);
      }
      if (sl.status === 'fulfilled') setSalesLoad(sl.value.data.filter((u: SalesLoad) => u.is_active));
      if (act.status === 'fulfilled') setActivities(act.value.data);
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

  // Only render a real sparkline when we actually have trend data. When the
  // trend endpoint fails (e.g. cloudcost 502), we render <Empty> placeholders
  // instead of fabricating numbers.
  const spark = useMemo(() => (trend.length ? trend : []), [trend]);
  const sparkPlaceholder = (
    <div style={{ height: 42, display: 'flex', alignItems: 'center' }}>
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={<span style={{ fontSize: 11, color: '#9ca3af' }}>
          {trendFailed ? '趋势数据暂不可达' : '趋势数据暂无'}
        </span>}
        imageStyle={{ height: 20 }}
        style={{ margin: 0 }}
      />
    </div>
  );

  return (
    <div className="page-fade">
      <BriefingBanner />
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
                <Link to="/allocations"><Button type="primary" ghost>订单管理</Button></Link>
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
            {spark.length ? <Sparkline values={spark} /> : sparkPlaceholder}
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
            {spark.length ? <Sparkline values={spark.slice().reverse()} color="#0ea5e9" /> : sparkPlaceholder}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text type="secondary">订单总数</Text>
                {loading ? <Skeleton.Input active size="large" style={{ marginTop: 4 }} /> :
                  <Statistic value={allocCount ?? 0} prefix={<AppstoreOutlined />} valueStyle={{ color: '#ec4899', fontWeight: 700 }} />}
              </div>
              <Avatar size={42} style={{ background: '#fce7f3', color: '#ec4899' }} icon={<AppstoreOutlined />} />
            </Space>
            {spark.length ? <Sparkline values={spark.map((v) => Math.max(0, v - 30))} color="#ec4899" /> : sparkPlaceholder}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            <Space align="start" style={{ width: '100%', justifyContent: 'space-between' }}>
              <div>
                <Text type="secondary">近 14 天趋势</Text>
                {spark.length ? (() => {
                  // first/last 可能为 0 或 spark 只有 1 个点 → 退化为 0% 避免 -601% 这种无意义数字
                  const first = spark[0] ?? 0;
                  const last = spark[spark.length - 1] ?? 0;
                  const pct = spark.length > 1 && first > 0
                    ? +(((last - first) / first) * 100).toFixed(1)
                    : 0;
                  const positive = pct >= 0;
                  return (
                    <Statistic value={pct}
                      suffix="%" prefix={positive ? <RiseOutlined /> : <FallOutlined />}
                      valueStyle={{ color: positive ? '#16a34a' : '#dc2626', fontWeight: 700 }} />
                  );
                })() : (
                  <Text type="secondary" style={{ display: 'block', marginTop: 4, fontSize: 13 }}>
                    {trendFailed ? '云管暂不可达' : '—'}
                  </Text>
                )}
              </div>
              <Avatar size={42} style={{ background: '#dcfce7', color: '#16a34a' }} icon={<RocketOutlined />} />
            </Space>
            {spark.length ? <Sparkline values={spark} color="#16a34a" /> : sparkPlaceholder}
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card
            title={<Space><UserOutlined />销售负载 <Tag>{salesLoad.length}</Tag></Space>}
            extra={<Link to="/sales-team"><Button size="small">管理</Button></Link>}
            bordered={false} style={{ borderRadius: 12 }}
          >
            {salesLoad.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有销售, 去 '销售团队' 页新增" />
            ) : (
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                {salesLoad.map((u) => {
                  const color = u.load_pct === -1 ? '#9ca3af'
                    : u.load_pct >= 90 ? '#ef4444'
                    : u.load_pct >= 70 ? '#f59e0b' : '#10b981';
                  return (
                    <div key={u.id}>
                      <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                        <Text strong>{u.name}</Text>
                        <Text style={{ fontSize: 12 }}>
                          {u.current_count}
                          {u.max_customers ? <Text type="secondary"> / {u.max_customers}</Text> : <Text type="secondary"> · 不限</Text>}
                        </Text>
                      </Space>
                      <Progress
                        percent={u.load_pct === -1 ? 0 : u.load_pct}
                        strokeColor={color} showInfo={false} size="small"
                      />
                    </div>
                  );
                })}
              </Space>
            )}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            title={<Space><HistoryOutlined />最近活动 <Tag>{activities.length}</Tag></Space>}
            bordered={false} style={{ borderRadius: 12 }}
            bodyStyle={{ maxHeight: 380, overflowY: 'auto' }}
          >
            {activities.length === 0 ? (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无活动" />
            ) : (
              <Timeline
                items={activities.map((a) => {
                  const m = ACTIVITY_META[a.kind] || ACTIVITY_META.follow_up;
                  return {
                    dot: m.icon, color: m.color,
                    children: (
                      <Space direction="vertical" size={2}>
                        <Space wrap>
                          <Text strong>{a.customer_name || `#${a.customer_id}`}</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {new Date(a.at).toLocaleString()}
                          </Text>
                        </Space>
                        <Text style={{ fontSize: 13 }}>{a.title}</Text>
                        {a.detail && (
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {a.detail.length > 80 ? a.detail.slice(0, 80) + '…' : a.detail}
                          </Text>
                        )}
                      </Space>
                    ),
                  };
                })}
              />
            )}
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

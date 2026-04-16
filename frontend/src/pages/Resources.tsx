import { useEffect, useMemo, useState } from 'react';
import { Button, Card, Col, Input, Row, Segmented, Select, Space, Statistic, Table, Tag, Typography, message } from 'antd';
import { CloudDownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { Pagination, Resource } from '../types';

const { Title, Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  AVAILABLE: 'green', ALLOCATED: 'blue', EXPIRED: 'default', FROZEN: 'red', EXHAUSTED: 'orange',
};

const PROVIDER_COLOR: Record<string, string> = {
  AWS: '#fa8c16',   // 橙
  AZURE: '#1677ff', // 蓝
  GCP: '#f5222d',   // 红
  ALIYUN: '#52c41a',
  UNKNOWN: '#8c8c8c',
};

const STATUS_PIE_COLOR: Record<string, string> = {
  AVAILABLE: '#52c41a',
  ALLOCATED: '#1677ff',
  EXPIRED: '#bfbfbf',
  FROZEN: '#f5222d',
  EXHAUSTED: '#fa8c16',
  UNKNOWN: '#d9d9d9',
};

interface ProviderRow {
  provider: string;
  total: number;
  by_status: Record<string, number>;
}

interface TopAvailable {
  id: number;
  resource_code: string;
  account_name?: string | null;
  provider?: string | null;
}

interface SummaryData {
  total: number;
  by_status: Record<string, number>;
  by_provider: ProviderRow[];
  top_available: TopAvailable[];
}

function StatusPie({ data, size = 180 }: { data: Record<string, number>; size?: number }) {
  const entries = Object.entries(data).filter(([, v]) => v > 0);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (total === 0) {
    return <Text type="secondary">暂无数据</Text>;
  }
  const cx = size / 2;
  const cy = size / 2;
  const r = size / 2 - 4;
  let startAngle = -Math.PI / 2;
  const paths: JSX.Element[] = [];
  entries.forEach(([k, v], idx) => {
    const angle = (v / total) * Math.PI * 2;
    const endAngle = startAngle + angle;
    const x1 = cx + r * Math.cos(startAngle);
    const y1 = cy + r * Math.sin(startAngle);
    const x2 = cx + r * Math.cos(endAngle);
    const y2 = cy + r * Math.sin(endAngle);
    const large = angle > Math.PI ? 1 : 0;
    const d = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`;
    paths.push(
      <path key={`${k}-${idx}`} d={d} fill={STATUS_PIE_COLOR[k] || '#d9d9d9'} stroke="#fff" strokeWidth={1} />,
    );
    startAngle = endAngle;
  });
  return (
    <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>{paths}</svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {entries.map(([k, v]) => (
          <div key={k} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                width: 12, height: 12, borderRadius: 2,
                background: STATUS_PIE_COLOR[k] || '#d9d9d9', display: 'inline-block',
              }}
            />
            <Text>{k}</Text>
            <Text type="secondary">{v} ({((v / total) * 100).toFixed(1)}%)</Text>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Resources() {
  const [view, setView] = useState<'看板' | '列表'>('看板');

  // List view state
  const [rows, setRows] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [provider, setProvider] = useState<string | undefined>();
  const [availOnly, setAvailOnly] = useState(false);
  const [syncing, setSyncing] = useState(false);

  // Board view state
  const [summary, setSummary] = useState<SummaryData | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Pagination<Resource>>('/api/resources', {
        params: {
          page, page_size: pageSize,
          keyword: keyword || undefined,
          cloud_provider: provider,
          available_only: availOnly || undefined,
        },
      });
      setRows(data.items); setTotal(data.total);
    } finally {
      setLoading(false);
    }
  };

  const loadSummary = async () => {
    setSummaryLoading(true);
    try {
      const { data } = await api.get<SummaryData>('/api/resources/summary');
      setSummary(data);
    } finally {
      setSummaryLoading(false);
    }
  };

  useEffect(() => {
    if (view === '列表') load();
    else loadSummary();
    /* eslint-disable-next-line */
  }, [view, page, pageSize, availOnly]);

  const stats = useMemo(() => {
    if (!summary) return { total: 0, available: 0, standby: 0, abnormal: 0 };
    const bs = summary.by_status || {};
    const known = (bs.AVAILABLE || 0) + (bs.STANDBY || 0);
    // 异常 = 非 AVAILABLE 非 STANDBY 的其它桶 (EXPIRED / FROZEN / EXHAUSTED / UNKNOWN 等)
    const abnormal = Math.max(summary.total - known, 0);
    return {
      total: summary.total,
      available: bs.AVAILABLE || 0,
      standby: bs.STANDBY || 0,
      abnormal,
    };
  }, [summary]);

  // 注: 不展示 total_quantity / allocated_quantity / available_quantity ——
  // 云管 ServiceAccount 模型没有数量字段, xiaoshou 本地列全是 NULL, 展示会误导.
  const columns = [
    { title: '货源编号', dataIndex: 'resource_code', width: 170 },
    { title: '类型', dataIndex: 'resource_type', width: 100 },
    { title: '云厂商', dataIndex: 'cloud_provider', width: 100 },
    { title: '账号', dataIndex: 'account_name' },
    { title: '单位成本', dataIndex: 'unit_cost', width: 100 },
    { title: '建议价', dataIndex: 'suggested_price', width: 100 },
    {
      title: '状态', dataIndex: 'resource_status', width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
  ];

  const topColumns = [
    { title: '货源编号', dataIndex: 'resource_code', width: 160 },
    { title: '账号', dataIndex: 'account_name' },
    {
      title: '云厂商', dataIndex: 'provider', width: 100,
      render: (p?: string | null) => p ? <Tag color={PROVIDER_COLOR[p] || 'default'}>{p}</Tag> : '-',
    },
  ];

  return (
    <Card>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>货源看板</Title>
          <Segmented
            options={['看板', '列表']}
            value={view}
            onChange={(v) => setView(v as '看板' | '列表')}
          />
        </Space>
        {view === '列表' ? (
          <Space>
            <Input
              placeholder="货源编号/账号"
              prefix={<SearchOutlined />}
              allowClear
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onPressEnter={() => { setPage(1); load(); }}
              style={{ width: 220 }}
            />
            <Select
              placeholder="云厂商" allowClear style={{ width: 120 }}
              value={provider}
              onChange={(v) => { setProvider(v); setPage(1); load(); }}
              options={['AZURE', 'AWS', 'GCP', 'ALIYUN'].map((v) => ({ value: v, label: v }))}
            />
            <Select
              style={{ width: 140 }}
              value={availOnly ? 'avail' : 'all'}
              onChange={(v) => setAvailOnly(v === 'avail')}
              options={[{ value: 'all', label: '全部货源' }, { value: 'avail', label: '仅可订购' }]}
            />
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            <Button
              icon={<CloudDownloadOutlined />} loading={syncing}
              onClick={async () => {
                setSyncing(true);
                try {
                  const { data } = await api.post('/api/sync/resources/from-cloudcost');
                  message.success(`从云管镜像：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`);
                  load();
                } finally { setSyncing(false); }
              }}
            >从云管同步</Button>
          </Space>
        ) : (
          <Space>
            <Button icon={<ReloadOutlined />} onClick={loadSummary} loading={summaryLoading}>刷新</Button>
          </Space>
        )}
      </Space>

      {view === '看板' ? (
        <div>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={12} md={6}>
              <Card size="small" loading={summaryLoading}>
                <Statistic title="总货源数" value={stats.total} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small" loading={summaryLoading}>
                <Statistic title="可用" value={stats.available} valueStyle={{ color: '#52c41a' }} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small" loading={summaryLoading}>
                <Statistic title="停用 (STANDBY)" value={stats.standby} valueStyle={{ color: '#8c8c8c' }} />
              </Card>
            </Col>
            <Col xs={12} md={6}>
              <Card size="small" loading={summaryLoading}>
                <Statistic title="异常" value={stats.abnormal} valueStyle={{ color: '#f5222d' }} />
              </Card>
            </Col>
          </Row>

          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col xs={24} md={14}>
              <Card size="small" title="按云厂商分布" loading={summaryLoading}>
                <Row gutter={[12, 12]}>
                  {(summary?.by_provider || []).map((p) => (
                    <Col xs={24} sm={12} md={8} key={p.provider}>
                      <Card
                        size="small"
                        style={{
                          borderLeft: `4px solid ${PROVIDER_COLOR[p.provider] || '#8c8c8c'}`,
                        }}
                      >
                        <Space direction="vertical" size={4} style={{ width: '100%' }}>
                          <Space style={{ justifyContent: 'space-between', width: '100%' }}>
                            <Tag color={PROVIDER_COLOR[p.provider] || 'default'}>{p.provider}</Tag>
                            <Text type="secondary">{p.total} 条</Text>
                          </Space>
                          {Object.entries(p.by_status || {}).map(([st, n]) => (
                            <Space key={st} style={{ justifyContent: 'space-between', width: '100%' }}>
                              <Tag color={STATUS_COLOR[st] || 'default'} style={{ margin: 0 }}>{st}</Tag>
                              <b>{n}</b>
                            </Space>
                          ))}
                        </Space>
                      </Card>
                    </Col>
                  ))}
                  {(!summary || summary.by_provider.length === 0) && (
                    <Col span={24}><Text type="secondary">暂无数据</Text></Col>
                  )}
                </Row>
              </Card>
            </Col>
            <Col xs={24} md={10}>
              <Card size="small" title="状态分布" loading={summaryLoading}>
                <StatusPie data={summary?.by_status || {}} />
              </Card>
            </Col>
          </Row>

          <Card size="small" title="Top 10 最近可用账号 (AVAILABLE)" loading={summaryLoading}>
            <Table<TopAvailable>
              rowKey="id"
              size="small"
              columns={topColumns}
              dataSource={summary?.top_available || []}
              pagination={false}
            />
          </Card>
        </div>
      ) : (
        <Table<Resource>
          rowKey="id" loading={loading} columns={columns} dataSource={rows}
          scroll={{ x: 1200 }}
          pagination={{
            current: page, pageSize, total, showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => { setPage(p); setPageSize(ps); },
          }}
        />
      )}
    </Card>
  );
}

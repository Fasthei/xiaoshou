import { useEffect, useState, useCallback } from 'react';
import {
  Card, Tabs, Select, Button, Space, Table, Spin, Empty,
  Typography, message as antdMessage,
} from 'antd';
import { ReloadOutlined, DownloadOutlined, BarChartOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import { DatePicker } from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import {
  LineChart, Line, BarChart, Bar, Cell, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { api } from '../api/axios';

const { RangePicker } = DatePicker;
const { Title, Text } = Typography;

// ─── Types ───────────────────────────────────────────────────────────────────

interface SalesTrendPoint {
  period: string;
  revenue: number;
  orders?: number;
  customers?: number;
}

interface ProfitPoint {
  period: string;
  revenue: number;
  cost?: number;
  profit: number;
  profit_rate?: number;
}

interface FunnelPoint {
  stage: string;
  count: number;
  label?: string;
}

interface YoyPoint {
  period: string;
  current_year: number;
  last_year: number;
  mom?: number;
  yoy?: number;
}

type DimensionOption = 'month' | 'quarter' | 'year' | 'salesperson';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function defaultRange(): [Dayjs, Dayjs] {
  return [dayjs().subtract(5, 'month').startOf('month'), dayjs().endOf('month')];
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return '—';
  return `¥${Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 0 })}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—';
  return `${(Number(v) * 100).toFixed(1)}%`;
}

const DIMENSION_OPTIONS: { label: string; value: DimensionOption }[] = [
  { label: '按月', value: 'month' },
  { label: '按季度', value: 'quarter' },
  { label: '按年', value: 'year' },
  { label: '按销售人员', value: 'salesperson' },
];

const COLORS = ['#0078D4', '#2B88D8', '#005A9E', '#107C10', '#C19C00', '#8C5A00'];

// ─── Sub-components ──────────────────────────────────────────────────────────

interface TabControlsProps {
  dimension: DimensionOption;
  onDimensionChange: (v: DimensionOption) => void;
  dateRange: [Dayjs, Dayjs];
  onDateRangeChange: (v: [Dayjs, Dayjs]) => void;
  onRefresh: () => void;
  onExport: () => void;
  loading: boolean;
  exportType: string;
}

function TabControls({
  dimension, onDimensionChange, dateRange, onDateRangeChange,
  onRefresh, onExport, loading, exportType,
}: TabControlsProps) {
  return (
    <Space wrap style={{ marginBottom: 16 }}>
      <Select<DimensionOption>
        value={dimension}
        onChange={onDimensionChange}
        options={DIMENSION_OPTIONS}
        style={{ width: 140 }}
      />
      <RangePicker
        value={dateRange}
        onChange={(vals) => {
          if (vals && vals[0] && vals[1]) {
            onDateRangeChange([vals[0], vals[1]]);
          }
        }}
        picker="month"
        allowClear={false}
      />
      <Button icon={<ReloadOutlined />} onClick={onRefresh} loading={loading}>
        刷新
      </Button>
      <Button
        icon={<DownloadOutlined />}
        onClick={onExport}
        type="default"
      >
        导出 CSV
      </Button>
    </Space>
  );
}

// ─── Sales Trend Tab ─────────────────────────────────────────────────────────

function SalesTrendTab() {
  const [dimension, setDimension] = useState<DimensionOption>('month');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(defaultRange());
  const [data, setData] = useState<SalesTrendPoint[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get<SalesTrendPoint[]>('/api/reports/sales-trend', {
        params: {
          dimension,
          start: dateRange[0].format('YYYY-MM'),
          end: dateRange[1].format('YYYY-MM'),
        },
      });
      setData(Array.isArray(res) ? res : (res as any)?.items || []);
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '加载销售趋势失败');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [dimension, dateRange]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    window.open(
      `/api/reports/export?type=sales-trend&format=csv&dimension=${dimension}&start=${dateRange[0].format('YYYY-MM')}&end=${dateRange[1].format('YYYY-MM')}`,
    );
  };

  const cols: ColumnsType<SalesTrendPoint> = [
    { title: '周期', dataIndex: 'period', width: 120 },
    { title: '营收', dataIndex: 'revenue', render: (v) => fmtMoney(v) },
    { title: '订单数', dataIndex: 'orders', render: (v) => v ?? '—' },
    { title: '客户数', dataIndex: 'customers', render: (v) => v ?? '—' },
  ];

  return (
    <>
      <TabControls
        dimension={dimension} onDimensionChange={setDimension}
        dateRange={dateRange} onDateRangeChange={setDateRange}
        onRefresh={load} onExport={exportCsv}
        loading={loading} exportType="sales-trend"
      />
      <Spin spinning={loading}>
        {data.length === 0 && !loading ? (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '40px 0' }} />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.2)" />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `¥${(v / 1000).toFixed(0)}k`} />
                <RTooltip formatter={(v: number) => fmtMoney(v)} />
                <Legend />
                <Line type="monotone" dataKey="revenue" name="营收" stroke={COLORS[0]} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
            <Table<SalesTrendPoint>
              rowKey="period"
              columns={cols}
              dataSource={data}
              size="small"
              pagination={false}
              style={{ marginTop: 16 }}
            />
          </>
        )}
      </Spin>
    </>
  );
}

// ─── Profit Analysis Tab ──────────────────────────────────────────────────────

function ProfitAnalysisTab() {
  const [dimension, setDimension] = useState<DimensionOption>('month');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(defaultRange());
  const [data, setData] = useState<ProfitPoint[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get<ProfitPoint[]>('/api/reports/profit-analysis', {
        params: {
          dimension,
          start: dateRange[0].format('YYYY-MM'),
          end: dateRange[1].format('YYYY-MM'),
        },
      });
      setData(Array.isArray(res) ? res : (res as any)?.items || []);
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '加载利润分析失败');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [dimension, dateRange]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    window.open(
      `/api/reports/export?type=profit-analysis&format=csv&dimension=${dimension}&start=${dateRange[0].format('YYYY-MM')}&end=${dateRange[1].format('YYYY-MM')}`,
    );
  };

  const cols: ColumnsType<ProfitPoint> = [
    { title: '周期', dataIndex: 'period', width: 120 },
    { title: '营收', dataIndex: 'revenue', render: (v) => fmtMoney(v) },
    { title: '成本', dataIndex: 'cost', render: (v) => fmtMoney(v) },
    { title: '利润', dataIndex: 'profit', render: (v) => fmtMoney(v) },
    { title: '利润率', dataIndex: 'profit_rate', render: (v) => fmtPct(v) },
  ];

  return (
    <>
      <TabControls
        dimension={dimension} onDimensionChange={setDimension}
        dateRange={dateRange} onDateRangeChange={setDateRange}
        onRefresh={load} onExport={exportCsv}
        loading={loading} exportType="profit-analysis"
      />
      <Spin spinning={loading}>
        {data.length === 0 && !loading ? (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '40px 0' }} />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.2)" />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `¥${(v / 1000).toFixed(0)}k`} />
                <RTooltip formatter={(v: number) => fmtMoney(v)} />
                <Legend />
                <Bar dataKey="revenue" name="营收" fill={COLORS[0]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="cost" name="成本" fill={COLORS[2]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="profit" name="利润" fill={COLORS[3]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <Table<ProfitPoint>
              rowKey="period"
              columns={cols}
              dataSource={data}
              size="small"
              pagination={false}
              style={{ marginTop: 16 }}
            />
          </>
        )}
      </Spin>
    </>
  );
}

// ─── Funnel Tab ───────────────────────────────────────────────────────────────

function FunnelTab() {
  const [dimension, setDimension] = useState<DimensionOption>('month');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(defaultRange());
  const [data, setData] = useState<FunnelPoint[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get<FunnelPoint[]>('/api/reports/funnel', {
        params: {
          dimension,
          start: dateRange[0].format('YYYY-MM'),
          end: dateRange[1].format('YYYY-MM'),
        },
      });
      setData(Array.isArray(res) ? res : (res as any)?.items || []);
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '加载漏斗数据失败');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [dimension, dateRange]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    window.open(
      `/api/reports/export?type=funnel&format=csv&dimension=${dimension}&start=${dateRange[0].format('YYYY-MM')}&end=${dateRange[1].format('YYYY-MM')}`,
    );
  };

  const cols: ColumnsType<FunnelPoint> = [
    { title: '阶段', dataIndex: 'stage', width: 160, render: (v, r) => r.label || v },
    { title: '客户数', dataIndex: 'count' },
  ];

  return (
    <>
      <TabControls
        dimension={dimension} onDimensionChange={setDimension}
        dateRange={dateRange} onDateRangeChange={setDateRange}
        onRefresh={load} onExport={exportCsv}
        loading={loading} exportType="funnel"
      />
      <Spin spinning={loading}>
        {data.length === 0 && !loading ? (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '40px 0' }} />
        ) : (
          <>
            {/* Funnel rendered as horizontal bar chart (BarChart with layout="vertical") */}
            <ResponsiveContainer width="100%" height={Math.max(240, data.length * 56)}>
              <BarChart
                layout="vertical"
                data={data}
                margin={{ top: 8, right: 40, left: 80, bottom: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.2)" />
                <XAxis type="number" tick={{ fontSize: 12 }} />
                <YAxis
                  type="category"
                  dataKey="stage"
                  tick={{ fontSize: 12 }}
                  tickFormatter={(v: string, i: number) => data[i]?.label || v}
                  width={76}
                />
                <RTooltip />
                <Bar dataKey="count" name="客户数" radius={[0, 4, 4, 0]}>
                  {data.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <Table<FunnelPoint>
              rowKey="stage"
              columns={cols}
              dataSource={data}
              size="small"
              pagination={false}
              style={{ marginTop: 16 }}
            />
          </>
        )}
      </Spin>
    </>
  );
}

// ─── YoY / MoM Tab ───────────────────────────────────────────────────────────

function YoyTab() {
  const [dimension, setDimension] = useState<DimensionOption>('month');
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>(defaultRange());
  const [data, setData] = useState<YoyPoint[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data: res } = await api.get<YoyPoint[]>('/api/reports/yoy', {
        params: {
          dimension,
          start: dateRange[0].format('YYYY-MM'),
          end: dateRange[1].format('YYYY-MM'),
        },
      });
      setData(Array.isArray(res) ? res : (res as any)?.items || []);
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '加载同比环比数据失败');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [dimension, dateRange]);

  useEffect(() => { load(); }, [load]);

  const exportCsv = () => {
    window.open(
      `/api/reports/export?type=yoy&format=csv&dimension=${dimension}&start=${dateRange[0].format('YYYY-MM')}&end=${dateRange[1].format('YYYY-MM')}`,
    );
  };

  const cols: ColumnsType<YoyPoint> = [
    { title: '周期', dataIndex: 'period', width: 120 },
    { title: '本年', dataIndex: 'current_year', render: (v) => fmtMoney(v) },
    { title: '去年同期', dataIndex: 'last_year', render: (v) => fmtMoney(v) },
    {
      title: '同比',
      dataIndex: 'yoy',
      render: (v) => {
        if (v == null) return '—';
        const pct = (Number(v) * 100).toFixed(1);
        const color = Number(v) >= 0 ? '#107C10' : '#A4262C';
        return <Text style={{ color }}>{Number(v) >= 0 ? '+' : ''}{pct}%</Text>;
      },
    },
    {
      title: '环比',
      dataIndex: 'mom',
      render: (v) => {
        if (v == null) return '—';
        const pct = (Number(v) * 100).toFixed(1);
        const color = Number(v) >= 0 ? '#107C10' : '#A4262C';
        return <Text style={{ color }}>{Number(v) >= 0 ? '+' : ''}{pct}%</Text>;
      },
    },
  ];

  return (
    <>
      <TabControls
        dimension={dimension} onDimensionChange={setDimension}
        dateRange={dateRange} onDateRangeChange={setDateRange}
        onRefresh={load} onExport={exportCsv}
        loading={loading} exportType="yoy"
      />
      <Spin spinning={loading}>
        {data.length === 0 && !loading ? (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} style={{ margin: '40px 0' }} />
        ) : (
          <>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.2)" />
                <XAxis dataKey="period" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} tickFormatter={(v) => `¥${(v / 1000).toFixed(0)}k`} />
                <RTooltip formatter={(v: number) => fmtMoney(v)} />
                <Legend />
                <Bar dataKey="current_year" name="本年" fill={COLORS[0]} radius={[4, 4, 0, 0]} />
                <Bar dataKey="last_year" name="去年同期" fill={COLORS[2]} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            <Table<YoyPoint>
              rowKey="period"
              columns={cols}
              dataSource={data}
              size="small"
              pagination={false}
              style={{ marginTop: 16 }}
            />
          </>
        )}
      </Spin>
    </>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

const TAB_ITEMS = [
  { key: 'sales-trend',     label: '销售趋势',   children: <SalesTrendTab /> },
  { key: 'profit-analysis', label: '利润分析',   children: <ProfitAnalysisTab /> },
  { key: 'funnel',          label: '漏斗',       children: <FunnelTab /> },
  { key: 'yoy',             label: '同比环比',   children: <YoyTab /> },
];

export default function Reports({ embedded = false }: { embedded?: boolean } = {}) {
  // `embedded = true` → 作为账单中心的一个 Tab 嵌入时不再渲染顶部 Hero banner，
  // 避免和外层 Bills.tsx 的英雄区重复；外层也已经有页面过渡动画，不再套 page-fade。
  const body = (
    <Card bordered={false} style={{ borderRadius: 12 }}>
      <Tabs
        defaultActiveKey="sales-trend"
        items={TAB_ITEMS}
        destroyInactiveTabPane
      />
    </Card>
  );

  if (embedded) return body;

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 4,
          marginBottom: 16,
          background: '#FFFFFF',
          border: '1px solid #E1DFDD',
          color: '#1F2937',
        }}
        styles={{ body: { padding: 20 } }}
      >
        <Space direction="vertical" size={4}>
          <Title level={3} style={{ color: '#1F2937', margin: 0 }}>
            <BarChartOutlined style={{ marginRight: 8, color: '#0078D4' }} />
            报表 BI
          </Title>
          <Text style={{ color: '#6B7280' }}>
            销售趋势 / 利润分析 / 漏斗 / 同比环比
          </Text>
        </Space>
      </Card>
      {body}
    </div>
  );
}

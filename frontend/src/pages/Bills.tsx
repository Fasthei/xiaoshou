import { useEffect, useMemo, useState } from 'react';
import {
  Card, Table, Tag, Typography, Space, DatePicker, Button, Select, Statistic,
  Row, Col, Empty, Skeleton, Divider, Result, Alert,
  message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, DollarOutlined, SearchOutlined, AppstoreOutlined,
  TeamOutlined, LineChartOutlined, CalculatorOutlined, DownloadOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { AxiosError } from 'axios';
import { api } from '../api/axios';
import DiscountCalculatorDrawer from '../components/DiscountCalculatorDrawer';

const { Title, Text } = Typography;

interface Bill {
  id: number;
  month: string;
  category_id?: number;
  provider: string;
  original_cost: number;
  markup_rate: number;
  final_cost: number;
  adjustment: number;
  status: string;
  confirmed_at?: string | null;
  notes?: string | null;
  created_at: string;
}

interface CustomerLite { id: number; customer_name: string; customer_code: string; industry?: string | null }
interface ResourceLite { id: number; resource_name: string; provider?: string }

interface UsageRecord {
  id: number; customer_id: number; resource_id: number;
  usage_date: string; usage_amount: string | number; usage_cost: string | number;
  unit?: string;
}

interface UsageSummary {
  customer_id?: number;
  total_usage?: string | number;
  total_cost?: string | number;
  record_count?: number;
  start_date?: string; end_date?: string;
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'default', confirmed: 'blue', paid: 'green',
};

export default function Bills() {
  // ---- cloudcost bills (existing) ----
  const [rows, setRows] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(false);
  const [month, setMonth] = useState<Dayjs | null>(dayjs());
  const [status, setStatus] = useState<string | undefined>();
  const [billsError, setBillsError] = useState<AxiosError<{ detail?: string }> | null>(null);
  const [calcOpen, setCalcOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  // ---- customer/resource drill-down (merged from Usage page) ----
  const [mode, setMode] = useState<'customer' | 'resource'>('customer');
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [resourceId, setResourceId] = useState<number | null>(null);
  const [customerOpts, setCustomerOpts] = useState<CustomerLite[]>([]);
  const [resourceOpts, setResourceOpts] = useState<ResourceLite[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [summary, setSummary] = useState<UsageSummary | null>(null);
  const [records, setRecords] = useState<UsageRecord[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const loadBills = async () => {
    setLoading(true);
    setBillsError(null);
    try {
      const { data } = await api.get<Bill[]>('/api/bridge/bills', {
        params: { month: month?.format('YYYY-MM'), status, page_size: 100 },
      });
      setRows(data);
    } catch (err) {
      setBillsError(err as AxiosError<{ detail?: string }>);
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadBills(); /* eslint-disable-next-line */ }, [month, status]);

  const handleExport = async () => {
    const m = month?.format('YYYY-MM');
    if (!m) {
      antdMessage.warning('请先选择月份');
      return;
    }
    setExporting(true);
    try {
      const token = localStorage.getItem('token') || sessionStorage.getItem('token') || '';
      const resp = await fetch(`/api/bills/export?month=${encodeURIComponent(m)}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
      if (resp.status === 404) {
        antdMessage.info('导出接口待上线 (GET /api/bills/export?month=YYYY-MM)');
        return;
      }
      if (!resp.ok) {
        antdMessage.error(`导出失败: HTTP ${resp.status}`);
        return;
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `bills-${m}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      antdMessage.success(`导出完成: bills-${m}.csv`);
    } catch (e: any) {
      antdMessage.error('导出失败: ' + (e?.message || '网络错误'));
    } finally {
      setExporting(false);
    }
  };

  const searchCustomers = async (kw: string) => {
    setSearchLoading(true);
    try {
      const { data } = await api.get('/api/customers', { params: { keyword: kw || undefined, page: 1, page_size: 20 } });
      setCustomerOpts(data.items || []);
    } finally {
      setSearchLoading(false);
    }
  };

  const searchResources = async (kw: string) => {
    setSearchLoading(true);
    try {
      const { data } = await api.get('/api/resources', { params: { keyword: kw || undefined, page: 1, page_size: 20 } });
      setResourceOpts(data.items || []);
    } finally {
      setSearchLoading(false);
    }
  };

  const loadCustomerDrill = async (id: number) => {
    setDetailLoading(true);
    try {
      const startOfMonth = month?.startOf('month').format('YYYY-MM-DD');
      const endOfMonth = month?.endOf('month').format('YYYY-MM-DD');
      const [sumR, listR] = await Promise.all([
        api.get(`/api/usage/customer/${id}/summary`, { params: { start_date: startOfMonth, end_date: endOfMonth } }),
        api.get(`/api/usage/customer/${id}`, { params: { start_date: startOfMonth, end_date: endOfMonth, page_size: 100 } }),
      ]);
      setSummary(sumR.data);
      setRecords(Array.isArray(listR.data) ? listR.data : (listR.data?.items || []));
    } finally {
      setDetailLoading(false);
    }
  };

  const loadResourceDrill = async (id: number) => {
    setDetailLoading(true);
    try {
      const startOfMonth = month?.startOf('month').format('YYYY-MM-DD');
      const endOfMonth = month?.endOf('month').format('YYYY-MM-DD');
      const { data } = await api.get(`/api/usage/resource/${id}`, {
        params: { start_date: startOfMonth, end_date: endOfMonth, page_size: 100 },
      });
      setSummary(null);
      setRecords(Array.isArray(data) ? data : (data?.items || []));
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    if (mode === 'customer' && customerId) loadCustomerDrill(customerId);
    if (mode === 'resource' && resourceId) loadResourceDrill(resourceId);
    // eslint-disable-next-line
  }, [mode, customerId, resourceId, month]);

  const total = rows.reduce((s, b) => s + Number(b.final_cost || 0), 0);
  const confirmed = rows.filter((b) => b.status === 'confirmed' || b.status === 'paid')
    .reduce((s, b) => s + Number(b.final_cost || 0), 0);

  const drillCost = useMemo(
    () => records.reduce((s, r) => s + Number(r.usage_cost || 0), 0),
    [records],
  );
  const drillAmount = useMemo(
    () => records.reduce((s, r) => s + Number(r.usage_amount || 0), 0),
    [records],
  );

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 12, marginBottom: 16,
          background: 'linear-gradient(120deg, #10b981 0%, #0ea5e9 100%)',
          color: 'white',
        }}
        styles={{ body: { padding: 24 } }}
      >
        <Row gutter={24}>
          <Col xs={24} md={12}>
            <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>BILLS · 账单与用量</Text>
            <Title level={2} style={{ color: 'white', margin: '4px 0 0' }}>
              <DollarOutlined /> 账单中心
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.8)' }}>
              月度账单（云管代理） + 按客户 / 货源下钻查用量明细
            </Text>
          </Col>
          <Col xs={24} md={6}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>本月应收</span>}
              value={total} precision={2} prefix="¥"
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
          <Col xs={24} md={6}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>已确认 / 已付</span>}
              value={confirmed} precision={2} prefix="¥"
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
        </Row>
      </Card>

      {/* 工具栏: 折扣计算器 + 导出 CSV */}
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<CalculatorOutlined />} onClick={() => setCalcOpen(true)}>
          折扣计算器
        </Button>
        <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
          导出 CSV
        </Button>
      </Space>

      {/* 按客户 / 货源下钻 */}
      <Card
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
        title={<Space><SearchOutlined /> 按客户 / 货源下钻</Space>}
        extra={<Text type="secondary" style={{ fontSize: 12 }}>选中后显示当月费用 + 使用明细</Text>}
      >
        <Space wrap size="middle" style={{ width: '100%' }}>
          <Select
            value={mode}
            onChange={(v) => { setMode(v); setCustomerId(null); setResourceId(null); setRecords([]); setSummary(null); }}
            style={{ width: 130 }}
            options={[
              { value: 'customer', label: <Space><TeamOutlined /> 客户</Space> },
              { value: 'resource', label: <Space><AppstoreOutlined /> 货源</Space> },
            ]}
          />
          {mode === 'customer' ? (
            <Select
              showSearch allowClear
              placeholder="搜索客户（名称 / 编号）"
              style={{ minWidth: 300 }}
              filterOption={false}
              loading={searchLoading}
              onSearch={searchCustomers}
              onChange={setCustomerId}
              onFocus={() => !customerOpts.length && searchCustomers('')}
              value={customerId || undefined}
              options={customerOpts.map((c) => ({
                value: c.id,
                label: `${c.customer_name} (${c.customer_code})${c.industry ? ' · ' + c.industry : ''}`,
              }))}
            />
          ) : (
            <Select
              showSearch allowClear
              placeholder="搜索货源（名称）"
              style={{ minWidth: 300 }}
              filterOption={false}
              loading={searchLoading}
              onSearch={searchResources}
              onChange={setResourceId}
              onFocus={() => !resourceOpts.length && searchResources('')}
              value={resourceId || undefined}
              options={resourceOpts.map((r) => ({
                value: r.id,
                label: `${r.resource_name}${r.provider ? ' · ' + r.provider : ''}`,
              }))}
            />
          )}
          <DatePicker picker="month" value={month} onChange={setMonth} placeholder="月份" />
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              if (mode === 'customer' && customerId) loadCustomerDrill(customerId);
              if (mode === 'resource' && resourceId) loadResourceDrill(resourceId);
            }}
          >刷新</Button>
        </Space>

        {(mode === 'customer' && !customerId) || (mode === 'resource' && !resourceId) ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={`请先选择一个${mode === 'customer' ? '客户' : '货源'}`}
            style={{ marginTop: 24 }}
          />
        ) : detailLoading ? (
          <Skeleton active style={{ marginTop: 24 }} />
        ) : (
          <>
            <Divider />
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col xs={24} md={8}>
                <Statistic title="当月总费用" value={drillCost} precision={2} prefix="¥"
                  valueStyle={{ color: '#ec4899' }} />
              </Col>
              <Col xs={24} md={8}>
                <Statistic title="用量合计" value={drillAmount} precision={2}
                  valueStyle={{ color: '#4f46e5' }} />
              </Col>
              <Col xs={24} md={8}>
                <Statistic title="明细条数" value={records.length}
                  prefix={<LineChartOutlined />} valueStyle={{ color: '#10b981' }} />
              </Col>
            </Row>
            <Table<UsageRecord>
              rowKey="id" size="small" dataSource={records}
              pagination={{ pageSize: 20, showSizeChanger: true }}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当月无用量" /> }}
              columns={[
                { title: '日期', dataIndex: 'usage_date', width: 120 },
                { title: '用量', dataIndex: 'usage_amount', width: 120,
                  render: (v: any, r) => `${Number(v).toFixed(2)}${r.unit ? ' ' + r.unit : ''}` },
                { title: '费用', dataIndex: 'usage_cost', width: 120,
                  render: (v: any) => <Text strong>¥{Number(v).toFixed(2)}</Text> },
                { title: '货源ID', dataIndex: 'resource_id', width: 100 },
                { title: '客户ID', dataIndex: 'customer_id', width: 100 },
              ]}
            />
          </>
        )}
      </Card>

      {/* 月度账单明细 */}
      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>月度账单（云管代理）</Title>
          <Space>
            <DatePicker picker="month" value={month} onChange={setMonth} />
            <Select placeholder="状态" allowClear style={{ width: 120 }} value={status} onChange={setStatus}
              options={['draft', 'confirmed', 'paid'].map((v) => ({ value: v, label: v }))} />
            <Button icon={<ReloadOutlined />} onClick={loadBills}>刷新</Button>
          </Space>
        </Space>
        {billsError ? (
          <Result
            status="500"
            title="云管账单暂不可达"
            subTitle={
              `${billsError.response?.status ? billsError.response.status + ' · ' : ''}` +
              `${billsError.response?.data?.detail || billsError.message || '稍后再试'}`
            }
            extra={<Button type="primary" icon={<ReloadOutlined />} onClick={loadBills}>重试</Button>}
          />
        ) : (
          <>
            {rows.length === 0 && !loading && (
              <Alert
                type="info" showIcon style={{ marginBottom: 12 }}
                message="本月暂无账单" description="若云管已切分月度账单仍无数据, 可稍后刷新重试。"
              />
            )}
            <Table<Bill>
              rowKey="id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
              columns={[
                { title: '月份', dataIndex: 'month', width: 110 },
                { title: '云厂商', dataIndex: 'provider', width: 100,
                  render: (v: string) => <Tag color="blue">{v}</Tag> },
                { title: '原始成本', dataIndex: 'original_cost', width: 120,
                  render: (v: number) => `¥${Number(v).toFixed(2)}` },
                { title: '加价倍率', dataIndex: 'markup_rate', width: 110,
                  render: (v: number) => `${Number(v).toFixed(2)}x` },
                { title: '调整', dataIndex: 'adjustment', width: 100,
                  render: (v: number) => `¥${Number(v).toFixed(2)}` },
                { title: '最终', dataIndex: 'final_cost', width: 120,
                  render: (v: number) => <Text strong>¥{Number(v).toFixed(2)}</Text> },
                { title: '状态', dataIndex: 'status', width: 110,
                  render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag> },
                { title: '创建', dataIndex: 'created_at', width: 170 },
              ]}
            />
          </>
        )}
      </Card>

      <DiscountCalculatorDrawer open={calcOpen} onClose={() => setCalcOpen(false)} />
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import {
  Card, Table, Tag, Typography, Space, DatePicker, Button, Statistic, Row, Col, Alert, Empty,
  Tooltip as AntTooltip, Tabs, Modal, Form, Input, InputNumber, Select, Switch, Slider,
  message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, AlertOutlined, PlusOutlined, CheckOutlined, BellOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip as RTooltip,
} from 'recharts';
import { api } from '../api/axios';

const { Title, Text } = Typography;

// ---------- types ----------
interface AlertRule {
  id: number;
  customer_id?: number | null;
  rule_name: string;
  rule_type: 'cost_upper' | 'cost_lower' | 'payment_overdue' | 'usage_surge' | 'contract_expiring';
  threshold_value?: number | null;
  threshold_unit?: string | null;
  enabled: boolean;
  notes?: string | null;
  created_at: string;
}

interface AlertEvent {
  id: number;
  alert_rule_id: number;
  alert_type: string;
  customer_id?: number | null;
  service?: string | null;
  month: string;
  actual_pct?: number | null;
  threshold_value?: number | null;
  message?: string | null;
  triggered_at: string;
}

interface Payment {
  id: number;
  customer_id: number;
  contract_id?: number | null;
  amount: number;
  expected_date: string;
  received_date?: string | null;
  status: 'pending' | 'received' | 'overdue' | 'cancelled';
  notes?: string | null;
  created_at: string;
}

interface CustomerLite { id: number; customer_name: string }

const RULE_TYPE_OPTIONS = [
  { label: '费用上限', value: 'cost_upper' },
  { label: '费用下限', value: 'cost_lower' },
  { label: '收款超期', value: 'payment_overdue' },
  { label: '用量激增', value: 'usage_surge' },
  { label: 'contract_expiring（合同到期提醒）', value: 'contract_expiring' },
];

const RULE_TYPE_COLOR: Record<string, string> = {
  cost_upper: 'red',
  cost_lower: 'blue',
  payment_overdue: 'orange',
  usage_surge: 'purple',
  contract_expiring: 'gold',
};

// ---------- my rules tab ----------
function MyRulesTab({ customers }: { customers: CustomerLite[] }) {
  const [rows, setRows] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedRuleType, setSelectedRuleType] = useState<string>('cost_upper');
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<AlertRule[]>('/api/alert-rules');
      setRows(data);
    } catch { /* handled globally */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const onCreate = async () => {
    try {
      const values = await form.validateFields();
      await api.post('/api/alert-rules', values);
      antdMessage.success('规则已创建');
      setModalOpen(false); form.resetFields(); setSelectedRuleType('cost_upper'); load();
    } catch (err) {
      if ((err as { errorFields?: unknown }).errorFields) return;
    }
  };

  const onModalCancel = () => {
    setModalOpen(false);
    form.resetFields();
    setSelectedRuleType('cost_upper');
  };

  const toggleEnabled = async (row: AlertRule, enabled: boolean) => {
    try {
      await api.patch(`/api/alert-rules/${row.id}`, { enabled });
      load();
    } catch { /* handled globally */ }
  };

  const onDelete = async (row: AlertRule) => {
    Modal.confirm({
      title: `删除规则「${row.rule_name}」?`,
      okButtonProps: { danger: true },
      onOk: async () => { await api.delete(`/api/alert-rules/${row.id}`); load(); },
    });
  };

  const customerName = (id?: number | null) =>
    id == null ? '全局' : (customers.find((c) => c.id === id)?.customer_name || `#${id}`);

  const isContractExpiring = selectedRuleType === 'contract_expiring';
  const isUsageSurge = selectedRuleType === 'usage_surge';

  const handleRuleTypeChange = (val: string) => {
    setSelectedRuleType(val);
    if (val === 'contract_expiring') {
      form.setFieldsValue({ threshold_unit: 'days' });
    } else if (val === 'usage_surge') {
      form.setFieldsValue({ threshold_unit: '%' });
    } else {
      form.setFieldsValue({ threshold_unit: 'CNY' });
    }
  };

  return (
    <>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={5} style={{ margin: 0 }}>自定义预警规则</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            新建规则
          </Button>
        </Space>
      </Space>

      <Table<AlertRule>
        rowKey="id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
        columns={[
          { title: '规则名', dataIndex: 'rule_name' },
          { title: '客户', dataIndex: 'customer_id', width: 180, render: customerName },
          {
            title: '类型', dataIndex: 'rule_type', width: 160,
            render: (v: string) => {
              const label = RULE_TYPE_OPTIONS.find((o) => o.value === v)?.label || v;
              const color = RULE_TYPE_COLOR[v] || 'default';
              return <Tag color={color}>{label}</Tag>;
            },
          },
          {
            title: '阈值', width: 140,
            render: (_, r) => r.threshold_value == null
              ? '-'
              : `${r.threshold_value} ${r.threshold_unit || ''}`.trim(),
          },
          {
            title: '启用', dataIndex: 'enabled', width: 80,
            render: (v: boolean, r) => (
              <Switch checked={v} onChange={(checked) => toggleEnabled(r, checked)} />
            ),
          },
          { title: '备注', dataIndex: 'notes', ellipsis: true },
          {
            title: '操作', width: 100,
            render: (_, r) => (
              <Button size="small" danger onClick={() => onDelete(r)}>删除</Button>
            ),
          },
        ]}
      />

      <Modal
        title="新建预警规则" open={modalOpen}
        onCancel={onModalCancel}
        onOk={onCreate} okText="创建"
      >
        <Form form={form} layout="vertical" initialValues={{ enabled: true, threshold_unit: 'CNY', rule_type: 'cost_upper' }}>
          <Form.Item name="rule_name" label="规则名" rules={[{ required: true, max: 200 }]}>
            <Input placeholder="如: 月费用超 10 万" />
          </Form.Item>
          <Form.Item name="rule_type" label="类型" rules={[{ required: true }]}>
            <Select options={RULE_TYPE_OPTIONS} onChange={handleRuleTypeChange} />
          </Form.Item>
          <Form.Item name="customer_id" label="客户 (留空=全局)">
            <Select
              allowClear showSearch optionFilterProp="label"
              options={customers.map((c) => ({ label: c.customer_name, value: c.id }))}
            />
          </Form.Item>
          <Space.Compact block>
            <Form.Item
              name="threshold_value"
              label={isContractExpiring ? '提前天数' : isUsageSurge ? '增长阈值 (%)' : '阈值'}
              style={{ flex: 2, marginRight: 8 }}
            >
              <InputNumber
                style={{ width: '100%' }}
                min={0}
                step={isContractExpiring ? 1 : 100}
                placeholder={isContractExpiring ? '如 30/60/90' : '数值'}
              />
            </Form.Item>
            <Form.Item name="threshold_unit" label="单位" style={{ flex: 1 }}>
              <Input placeholder={isContractExpiring ? 'days' : isUsageSurge ? '%' : 'CNY'} />
            </Form.Item>
          </Space.Compact>
          <Form.Item name="enabled" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

// ---------- triggered events tab ----------
function TriggeredEventsTab({ customers }: { customers: CustomerLite[] }) {
  const [rows, setRows] = useState<AlertEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [alertTypeFilter, setAlertTypeFilter] = useState<string | undefined>(undefined);

  const load = async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (alertTypeFilter) params.alert_type = alertTypeFilter;
      const { data } = await api.get<AlertEvent[]>('/api/alert-rules/triggered', { params });
      setRows(data);
    } catch { /* handled globally */ }
    finally { setLoading(false); }
  };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [alertTypeFilter]);

  const customerName = (id?: number | null) =>
    id == null ? '-' : (customers.find((c) => c.id === id)?.customer_name || `#${id}`);

  return (
    <>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={5} style={{ margin: 0 }}>触发记录（近 30 天）</Title>
        <Space>
          <Select
            placeholder="按类型过滤" allowClear style={{ width: 200 }}
            value={alertTypeFilter} onChange={setAlertTypeFilter}
            options={[
              { label: '用量激增', value: 'usage_surge' },
              { label: '合同到期提醒', value: 'contract_expiring' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </Space>

      <Table<AlertEvent>
        rowKey="id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
        columns={[
          {
            title: '类型', dataIndex: 'alert_type', width: 140,
            render: (v: string) => {
              const label = v === 'usage_surge' ? '用量激增' : v === 'contract_expiring' ? '合同到期' : v;
              const color = RULE_TYPE_COLOR[v] || 'default';
              return <Tag color={color}>{label}</Tag>;
            },
          },
          { title: '客户', dataIndex: 'customer_id', width: 180, render: customerName },
          { title: '服务/对象', dataIndex: 'service', width: 120, render: (v: string | null) => v || '-' },
          { title: '月份', dataIndex: 'month', width: 90 },
          {
            title: '告警信息', dataIndex: 'message', ellipsis: true,
            render: (v: string | null) => v || '-',
          },
          {
            title: '触发时间', dataIndex: 'triggered_at', width: 170,
            render: (v: string) => v ? dayjs(v).format('YYYY-MM-DD HH:mm') : '-',
          },
        ]}
      />
    </>
  );
}

// ---------- payments tab ----------
function PaymentsTab({ customers }: { customers: CustomerLite[] }) {
  const [rows, setRows] = useState<Payment[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [form] = Form.useForm();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Payment[]>('/api/payments', {
        params: statusFilter ? { status: statusFilter } : {},
      });
      setRows(data);
    } catch { /* handled globally */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter]);

  const onCreate = async () => {
    try {
      const values = await form.validateFields();
      const payload = {
        ...values,
        expected_date: values.expected_date?.format('YYYY-MM-DD'),
        received_date: values.received_date?.format('YYYY-MM-DD'),
      };
      await api.post('/api/payments', payload);
      antdMessage.success('收款已登记');
      setModalOpen(false); form.resetFields(); load();
    } catch (err) {
      if ((err as { errorFields?: unknown }).errorFields) return;
    }
  };

  const markReceived = async (row: Payment) => {
    await api.patch(`/api/payments/${row.id}`, { mark_received: true });
    antdMessage.success('已登记收款');
    load();
  };

  const today = dayjs().startOf('day');
  const customerName = (id: number) =>
    customers.find((c) => c.id === id)?.customer_name || `#${id}`;

  return (
    <>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={5} style={{ margin: 0 }}>收款与超期管理</Title>
        <Space>
          <Select
            placeholder="状态过滤" allowClear style={{ width: 140 }}
            value={statusFilter} onChange={setStatusFilter}
            options={[
              { label: '待收款', value: 'pending' },
              { label: '已收款', value: 'received' },
              { label: '超期', value: 'overdue' },
              { label: '取消', value: 'cancelled' },
            ]}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
            登记收款
          </Button>
        </Space>
      </Space>

      <Table<Payment>
        rowKey="id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
        rowClassName={(r) => {
          const overdue = r.status === 'pending' && dayjs(r.expected_date).isBefore(today);
          return overdue ? 'xs-payment-overdue' : '';
        }}
        columns={[
          { title: '客户', dataIndex: 'customer_id', width: 180, render: (v: number) => customerName(v) },
          { title: '合同', dataIndex: 'contract_id', width: 100, render: (v) => v ?? '-' },
          { title: '金额', dataIndex: 'amount', width: 120, render: (v: number) => <Text strong>{v}</Text> },
          {
            title: '预期日期', dataIndex: 'expected_date', width: 130,
            render: (v: string, r) => {
              const overdue = r.status === 'pending' && dayjs(v).isBefore(today);
              return overdue ? <Text style={{ color: '#A4262C' }}>{v}（超期）</Text> : v;
            },
          },
          { title: '实收日期', dataIndex: 'received_date', width: 130, render: (v: string | null) => v || '-' },
          {
            title: '状态', dataIndex: 'status', width: 110,
            render: (v: Payment['status'], r) => {
              const overdue = v === 'pending' && dayjs(r.expected_date).isBefore(today);
              if (overdue) return <Tag color="red">超期</Tag>;
              const map: Record<Payment['status'], { color: string; label: string }> = {
                pending: { color: 'orange', label: '待收款' },
                received: { color: 'green', label: '已收款' },
                overdue: { color: 'red', label: '超期' },
                cancelled: { color: 'default', label: '取消' },
              };
              const s = map[v] || { color: 'default', label: v };
              return <Tag color={s.color}>{s.label}</Tag>;
            },
          },
          { title: '备注', dataIndex: 'notes', ellipsis: true },
          {
            title: '操作', width: 120,
            render: (_, r) => r.status !== 'received' ? (
              <Button size="small" type="link" icon={<CheckOutlined />}
                onClick={() => markReceived(r)}>
                登记收款
              </Button>
            ) : null,
          },
        ]}
      />

      <style>{`.xs-payment-overdue td { background: #fef2f2 !important; }`}</style>

      <Modal
        title="登记收款" open={modalOpen}
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        onOk={onCreate} okText="登记"
      >
        <Form form={form} layout="vertical" initialValues={{ status: 'pending' }}>
          <Form.Item name="customer_id" label="客户" rules={[{ required: true }]}>
            <Select
              showSearch optionFilterProp="label"
              options={customers.map((c) => ({ label: c.customer_name, value: c.id }))}
            />
          </Form.Item>
          <Form.Item name="contract_id" label="合同 ID (可选)">
            <InputNumber style={{ width: '100%' }} min={1} />
          </Form.Item>
          <Form.Item name="amount" label="金额" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={0} step={100} />
          </Form.Item>
          <Form.Item name="expected_date" label="预期收款日期" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="received_date" label="实收日期 (可选)">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="status" label="状态">
            <Select options={[
              { label: '待收款', value: 'pending' },
              { label: '已收款', value: 'received' },
              { label: '超期', value: 'overdue' },
              { label: '取消', value: 'cancelled' },
            ]} />
          </Form.Item>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}

// ---------- usage breakdown tab (按 SKU 粒度的横向条形图) ----------
// 数据结构对应后端 /api/usage/breakdown。
// 每个 resource 下挂一个 skus 数组，每个 SKU 已按 (provider, product, sku,
// region, usage_unit) 去重聚合过，附带 category 类目（compute/ai/...）。

interface UsageSku {
  provider: string | null;
  product: string;
  sku: string;
  region: string | null;
  usage_unit: string | null;
  category: 'compute' | 'ai' | 'database' | 'storage' | 'network' | 'other';
  category_label: string;
  cost: number;
  usage: number;
  record_count: number;
}

interface UsageResourceRow {
  resource_id: number;
  resource_code: string | null;
  account_name: string | null;
  cloud_provider: string | null;
  identifier_field: string | null;
  total_cost: number;
  total_usage: number;
  sku_count: number;
  skus: UsageSku[];
}

interface UsageCustomerRow {
  customer_id: number;
  customer_name: string;
  customer_code: string | null;
  customer_type?: string | null;
  total_cost: number;
  total_usage: number;
  resource_count: number;
  resources: UsageResourceRow[];
}

interface UsageBreakdownResp {
  month: string;
  total_cost: number;
  total_usage: number;
  customer_count: number;
  categories: string[];
  category_labels: Record<string, string>;
  customers: UsageCustomerRow[];
}

// recharts 用的 hex 色（和账单里的 antd color 对应）
const CATEGORY_HEX: Record<string, string> = {
  compute:  '#2F54EB',
  ai:       '#EB2F96',
  database: '#13C2C2',
  storage:  '#FAAD14',
  network:  '#52C41A',
  other:    '#8C8C8C',
};
const CATEGORY_ANTD_COLOR: Record<string, string> = {
  compute:  'geekblue',
  ai:       'magenta',
  database: 'cyan',
  storage:  'gold',
  network:  'green',
  other:    'default',
};

// 单行条形图 datum。Y 轴上只显示 product + sku，客户/货源塞进 tooltip.
interface SkuBarDatum {
  key: string;           // 唯一键 = customer|resource|provider|product|sku|region|unit
  customer: string;
  resource: string;
  provider: string;
  product: string;
  productShort: string;  // 去掉括号内容后的短形式，Y 轴第一行展示
  sku: string;
  skuShort: string;      // 长 SKU 截短
  region: string;
  unit: string;
  cost: number;
  usage: number;
  category: string;
  category_label: string;
}

// 把 "Claude Opus 4.6 (Amazon Bedrock Edition)" → "Claude Opus 4.6"
function trimProduct(s: string): string {
  return s.replace(/\s*\([^)]*\)\s*/g, '').trim() || s;
}
// 把过长 SKU 截断
function trimSku(s: string, max = 40): string {
  if (!s) return '';
  return s.length <= max ? s : s.slice(0, max - 1) + '…';
}

function UsageBreakdownTab() {
  const [month, setMonth] = useState<Dayjs | null>(dayjs());
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState<UsageBreakdownResp | null>(null);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  // 筛选：选客户 / 货源 / 服务名称（云管 product 字段，非本地推断的类目）；TopN 控制条数
  const [filterCustomerId, setFilterCustomerId] = useState<number | undefined>(undefined);
  const [filterResourceId, setFilterResourceId] = useState<number | undefined>(undefined);
  const [filterProducts, setFilterProducts] = useState<string[]>([]);
  const [topN, setTopN] = useState<number>(30);

  const load = async () => {
    const m = month?.format('YYYY-MM');
    if (!m) return;
    setLoading(true);
    setErrMsg(null);
    try {
      const { data } = await api.get<UsageBreakdownResp>('/api/usage/breakdown', { params: { month: m } });
      setResp(data);
    } catch (e: any) {
      setErrMsg(e?.response?.data?.detail || e?.message || '加载失败');
      setResp(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [month]);

  // 客户/货源列表用于筛选下拉
  const customerOptions = useMemo(
    () => (resp?.customers ?? []).map((c) => ({ label: c.customer_name, value: c.customer_id })),
    [resp],
  );
  const resourceOptions = useMemo(() => {
    const pool = filterCustomerId
      ? resp?.customers.filter((c) => c.customer_id === filterCustomerId) ?? []
      : resp?.customers ?? [];
    return pool.flatMap((c) => c.resources.map((r) => ({
      label: `${r.resource_code ?? r.identifier_field ?? '(无编号)'} · ${r.account_name ?? '-'}`,
      value: r.resource_id,
    })));
  }, [resp, filterCustomerId]);

  // 服务名称下拉（来自云管真实 product，跟着客户/货源联动）。
  // 按字母排序 + 去重 —— 是云管 metering.product 原样，不做本地分类加工。
  const productOptions = useMemo(() => {
    const pool = filterCustomerId
      ? resp?.customers.filter((c) => c.customer_id === filterCustomerId) ?? []
      : resp?.customers ?? [];
    const set = new Set<string>();
    for (const c of pool) {
      for (const r of c.resources) {
        if (filterResourceId !== undefined && r.resource_id !== filterResourceId) continue;
        for (const s of r.skus) {
          if (s.product) set.add(s.product);
        }
      }
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b)).map((p) => ({ label: p, value: p }));
  }, [resp, filterCustomerId, filterResourceId]);

  // 扁平化 → 按筛选 + topN 裁剪
  const chartData: SkuBarDatum[] = useMemo(() => {
    if (!resp) return [];
    const prodFilter = new Set(filterProducts);
    const rows: SkuBarDatum[] = [];
    for (const c of resp.customers) {
      if (filterCustomerId !== undefined && c.customer_id !== filterCustomerId) continue;
      for (const r of c.resources) {
        if (filterResourceId !== undefined && r.resource_id !== filterResourceId) continue;
        for (const s of r.skus) {
          if (prodFilter.size > 0 && !prodFilter.has(s.product)) continue;
          rows.push({
            key: [c.customer_id, r.resource_id, s.provider ?? '', s.product, s.sku, s.region ?? '', s.usage_unit ?? ''].join('|'),
            customer: c.customer_name,
            resource: r.resource_code ?? r.account_name ?? r.identifier_field ?? '',
            provider: s.provider ?? '',
            product: s.product,
            productShort: trimProduct(s.product),
            sku: s.sku,
            skuShort: trimSku(s.sku),
            region: s.region ?? '',
            unit: s.usage_unit ?? '',
            cost: s.cost,
            usage: s.usage,
            category: s.category,
            category_label: s.category_label,
          });
        }
      }
    }
    rows.sort((a, b) => b.cost - a.cost);
    return rows.slice(0, topN);
  }, [resp, filterCustomerId, filterResourceId, filterProducts, topN]);

  // 图表高度 = 每行约 44px（两行标签 + 间距），最小 380
  const chartHeight = Math.max(380, chartData.length * 44 + 40);

  // 自定义 Y 轴 tick：两行 SVG text（第一行产品短名，第二行 SKU 短形）
  // recharts tick 要求返回 ReactElement（不接受 null），找不到 datum 时返回空 <g/>
  const renderYTick = ({ x, y, payload }: any) => {
    const d = chartData.find((row) => row.key === payload.value);
    if (!d) return <g />;
    return (
      <g transform={`translate(${x},${y})`}>
        <text x={-8} y={-2} textAnchor="end" fontSize={12} fill="#1F2937" fontWeight={500}>
          {d.productShort}
        </text>
        <text x={-8} y={14} textAnchor="end" fontSize={10.5} fill="#6B7280">
          {d.skuShort}
        </text>
      </g>
    );
  };

  // 自定义 Tooltip：结构化展示所有维度
  const renderTooltip = ({ active, payload }: any) => {
    if (!active || !payload || !payload.length) return null;
    const d: SkuBarDatum = payload[0].payload;
    return (
      <div style={{
        background: '#fff', border: '1px solid #E1DFDD', borderRadius: 6,
        padding: '8px 12px', boxShadow: '0 2px 8px rgba(0,0,0,0.08)', maxWidth: 360,
      }}>
        <div style={{ marginBottom: 4 }}>
          <Tag color={CATEGORY_ANTD_COLOR[d.category] || 'default'} style={{ marginRight: 4 }}>
            {d.category_label}
          </Tag>
          {d.provider && <Tag>{d.provider}</Tag>}
          {d.region && <Tag>{d.region}</Tag>}
        </div>
        <div style={{ fontSize: 13, fontWeight: 600, color: '#1F2937' }}>{d.product}</div>
        <div style={{ fontSize: 11, color: '#6B7280', marginBottom: 6, wordBreak: 'break-all' }}>{d.sku}</div>
        <div style={{ fontSize: 12, color: '#1F2937' }}>
          <b>客户</b>：{d.customer}
        </div>
        <div style={{ fontSize: 12, color: '#1F2937' }}>
          <b>货源</b>：{d.resource || '-'}
        </div>
        <div style={{ marginTop: 6, fontSize: 13 }}>
          <b>¥ {d.cost.toFixed(2)}</b>
          {d.usage > 0 && (
            <span style={{ color: '#6B7280', marginLeft: 8 }}>
              用量 {d.usage.toFixed(4)} {d.unit}
            </span>
          )}
        </div>
      </div>
    );
  };


  return (
    <div>
      <Row gutter={12} style={{ marginBottom: 16 }}>
        <Col xs={24} md={8}>
          <Card bordered size="small">
            <Statistic
              title={<Text type="secondary">当月总费用</Text>}
              value={resp?.total_cost ?? 0} precision={2} prefix="¥"
              valueStyle={{ fontWeight: 600 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card bordered size="small">
            <Statistic
              title={<Text type="secondary">客户数</Text>}
              value={resp?.customer_count ?? 0}
              valueStyle={{ fontWeight: 600 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card bordered size="small">
            <Statistic
              title={<Text type="secondary">SKU 条数（筛选后 / 共显示）</Text>}
              value={chartData.length}
              valueStyle={{ fontWeight: 600 }}
            />
          </Card>
        </Col>
      </Row>

      {/* 按云管 product 聚合 Top 5 占比 —— 真实服务名，不做本地类目推断 */}
      {chartData.length > 0 && (
        <Card size="small" bordered style={{ marginBottom: 16 }}>
          <Space wrap size={6}>
            <Text type="secondary">Top 服务占比：</Text>
            {(() => {
              const byProd: Record<string, number> = {};
              chartData.forEach((d) => { byProd[d.product] = (byProd[d.product] || 0) + d.cost; });
              const total = Object.values(byProd).reduce((s, v) => s + v, 0);
              const top = Object.entries(byProd)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 5);
              return top.map(([name, v]) => {
                const pct = total > 0 ? (v / total) * 100 : 0;
                return (
                  <AntTooltip key={name} title={`¥${v.toFixed(2)} · ${pct.toFixed(1)}%`}>
                    <Tag>{trimProduct(name)}: ¥{v.toFixed(2)}（{pct.toFixed(1)}%）</Tag>
                  </AntTooltip>
                );
              });
            })()}
          </Space>
        </Card>
      )}

      <Card
        bordered={false}
        style={{ borderRadius: 12 }}
        title={<Title level={5} style={{ margin: 0 }}>SKU 费用分布（客户 × 货源 × 服务 × SKU）</Title>}
        extra={
          <Space wrap>
            <DatePicker picker="month" value={month} onChange={setMonth} allowClear={false} />
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Space>
        }
      >
        {/* 筛选行 */}
        <Row gutter={[12, 8]} style={{ marginBottom: 12 }}>
          <Col xs={24} md={6}>
            <Select
              allowClear showSearch placeholder="筛选客户" style={{ width: '100%' }}
              options={customerOptions} value={filterCustomerId}
              onChange={(v) => { setFilterCustomerId(v); setFilterResourceId(undefined); }}
              filterOption={(input, opt) =>
                String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Col>
          <Col xs={24} md={6}>
            <Select
              allowClear showSearch placeholder="筛选货源" style={{ width: '100%' }}
              options={resourceOptions} value={filterResourceId}
              onChange={setFilterResourceId}
              filterOption={(input, opt) =>
                String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Col>
          <Col xs={24} md={6}>
            <Select
              allowClear showSearch mode="multiple"
              placeholder="筛选服务（云管 product）" style={{ width: '100%' }}
              value={filterProducts} onChange={setFilterProducts}
              options={productOptions}
              maxTagCount="responsive"
              filterOption={(input, opt) =>
                String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())}
            />
          </Col>
          <Col xs={24} md={6}>
            <Space style={{ width: '100%' }}>
              <Text type="secondary">Top N</Text>
              <Slider
                min={5} max={100} step={5}
                value={topN} onChange={(v) => setTopN(Number(v))}
                style={{ flex: 1, minWidth: 120 }}
              />
              <Text strong>{topN}</Text>
            </Space>
          </Col>
        </Row>

        {errMsg && (
          <Alert type="error" showIcon style={{ marginBottom: 12 }}
            message="加载失败" description={errMsg} />
        )}
        {resp && resp.customers.length === 0 && !loading && !errMsg && (
          <Alert
            type="info" showIcon style={{ marginBottom: 12 }}
            message="本月暂无用量数据"
            description='确认客户已在客户详情的"关联货源"勾选，并且云管 cc_usage 已同步（账单中心"同步云管"按钮）。'
          />
        )}
        {!loading && chartData.length === 0 && resp && resp.customers.length > 0 && (
          <Alert type="info" showIcon style={{ marginBottom: 12 }}
            message="当前筛选下没有 SKU"
            description="放宽筛选条件或调大 TopN。" />
        )}

        {/* 条形图 —— 水平方向；Y 轴两行 (产品/SKU)，X 轴是费用；Tooltip 给全部维度 */}
        {chartData.length > 0 && (
          <div style={{ width: '100%', height: chartHeight }}>
            <ResponsiveContainer>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 8, right: 40, left: 8, bottom: 8 }}
                barCategoryGap="30%"
              >
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis
                  type="number"
                  tickFormatter={(v) => `¥${Number(v).toFixed(0)}`}
                />
                <YAxis
                  type="category"
                  dataKey="key"
                  width={260}
                  interval={0}
                  tick={renderYTick}
                />
                <RTooltip content={renderTooltip} />
                <Bar dataKey="cost" name="费用" radius={[0, 4, 4, 0]}>
                  {chartData.map((d) => (
                    <Cell key={d.key} fill={CATEGORY_HEX[d.category] || CATEGORY_HEX.other} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  );
}

// ---------- page root ----------
export default function Alerts() {
  const [customers, setCustomers] = useState<CustomerLite[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get<Array<CustomerLite & Record<string, unknown>>>('/api/customers');
        setCustomers(data.map((c) => ({ id: c.id, customer_name: c.customer_name })));
      } catch { /* handled globally */ }
    })();
  }, []);

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 4, marginBottom: 16,
          background: '#FFFFFF',
          border: '1px solid #E1DFDD',
          color: '#1F2937',
        }}
        styles={{ body: { padding: 20 } }}
      >
        <Space direction="vertical" size={4}>
          <Text style={{ color: '#6B7280', letterSpacing: 4 }}>ALERTS · 预警中心</Text>
          <Title level={2} style={{ color: '#1F2937', margin: 0 }}>
            <AlertOutlined style={{ color: '#A4262C' }} /> 预警与收款
          </Title>
          <Text style={{ color: '#6B7280' }}>
            自定义规则 · 收款超期追踪
          </Text>
        </Space>
      </Card>

      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Tabs
          defaultActiveKey="usage-breakdown"
          items={[
            { key: 'usage-breakdown', label: <><BarChartOutlined /> 用量查看</>, children: <UsageBreakdownTab /> },
            { key: 'my-rules', label: '我的规则', children: <MyRulesTab customers={customers} /> },
            { key: 'payments', label: '收款超期', children: <PaymentsTab customers={customers} /> },
            { key: 'triggered', label: <><BellOutlined /> 触发记录</>, children: <TriggeredEventsTab customers={customers} /> },
          ]}
        />
      </Card>
    </div>
  );
}

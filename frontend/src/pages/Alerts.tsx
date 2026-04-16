import { useEffect, useState } from 'react';
import {
  Card, Table, Tag, Typography, Progress, Space, DatePicker, Button, Empty, Result,
  Tabs, Modal, Form, Input, InputNumber, Select, Switch, message as antdMessage,
} from 'antd';
import { ReloadOutlined, AlertOutlined, PlusOutlined, CheckOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { AxiosError } from 'axios';
import { api } from '../api/axios';

const { Title, Text } = Typography;

// ---------- types ----------
interface RuleStatus {
  rule_id: number;
  rule_name: string;
  threshold_type: string;
  threshold_value: number;
  actual: number;
  pct: number;
  triggered: boolean;
  account_name?: string | null;
  provider?: string | null;
  external_project_id?: string | null;
}

interface AlertRule {
  id: number;
  customer_id?: number | null;
  rule_name: string;
  rule_type: 'cost_upper' | 'cost_lower' | 'payment_overdue';
  threshold_value?: number | null;
  threshold_unit?: string | null;
  enabled: boolean;
  notes?: string | null;
  created_at: string;
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
];

// ---------- cloudcost tab (existing behaviour) ----------
function CloudcostTab() {
  const [rows, setRows] = useState<RuleStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [month, setMonth] = useState<Dayjs | null>(dayjs());
  const [error, setError] = useState<AxiosError<{ detail?: string }> | null>(null);

  const load = async () => {
    setLoading(true); setError(null);
    try {
      const { data } = await api.get<RuleStatus[]>('/api/bridge/alerts', {
        params: { month: month?.format('YYYY-MM') },
      });
      setRows(data);
    } catch (err) {
      setError(err as AxiosError<{ detail?: string }>); setRows([]);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [month]);

  if (error) {
    const status = error.response?.status;
    const detail = error.response?.data?.detail || error.message || '稍后再试';
    return (
      <Result
        status="500"
        title="云管暂不可达"
        subTitle={`${status ? status + ' · ' : ''}${detail}`}
        extra={
          <Space>
            <DatePicker picker="month" value={month} onChange={setMonth} />
            <Button type="primary" icon={<ReloadOutlined />} onClick={load}>重试</Button>
          </Space>
        }
      />
    );
  }

  return (
    <>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={5} style={{ margin: 0 }}>云管规则状态</Title>
        <Space>
          <DatePicker picker="month" value={month} onChange={setMonth} />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </Space>
      {rows.length === 0 && !loading ? (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该月无预警规则或云管未配置" />
      ) : (
        <Table<RuleStatus>
          rowKey="rule_id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
          columns={[
            { title: '规则', dataIndex: 'rule_name' },
            { title: '类型', dataIndex: 'threshold_type', width: 180, render: (v) => <Tag color="geekblue">{v}</Tag> },
            { title: '账号', dataIndex: 'account_name', width: 180 },
            { title: '阈值', dataIndex: 'threshold_value', width: 100 },
            { title: '实际', dataIndex: 'actual', width: 100 },
            {
              title: '完成度', dataIndex: 'pct', width: 200,
              render: (v: number) => (
                <Progress
                  percent={Math.min(Math.round(v), 100)} size="small"
                  status={v >= 100 ? 'exception' : v >= 80 ? 'active' : 'normal'}
                />
              ),
            },
            {
              title: '状态', dataIndex: 'triggered', width: 110,
              render: (t: boolean, r) =>
                t ? <Tag color="red">已触发</Tag>
                  : (r.pct || 0) >= 80 ? <Tag color="orange">接近</Tag>
                  : <Tag color="green">正常</Tag>,
            },
          ]}
        />
      )}
    </>
  );
}

// ---------- my rules tab ----------
function MyRulesTab({ customers }: { customers: CustomerLite[] }) {
  const [rows, setRows] = useState<AlertRule[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
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
      setModalOpen(false); form.resetFields(); load();
    } catch (err) {
      if ((err as { errorFields?: unknown }).errorFields) return;
    }
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
            title: '类型', dataIndex: 'rule_type', width: 120,
            render: (v: string) => {
              const label = RULE_TYPE_OPTIONS.find((o) => o.value === v)?.label || v;
              const color = v === 'cost_upper' ? 'red' : v === 'cost_lower' ? 'blue' : 'orange';
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
        onCancel={() => { setModalOpen(false); form.resetFields(); }}
        onOk={onCreate} okText="创建"
      >
        <Form form={form} layout="vertical" initialValues={{ enabled: true, threshold_unit: 'CNY' }}>
          <Form.Item name="rule_name" label="规则名" rules={[{ required: true, max: 200 }]}>
            <Input placeholder="如: 月费用超 10 万" />
          </Form.Item>
          <Form.Item name="rule_type" label="类型" rules={[{ required: true }]}>
            <Select options={RULE_TYPE_OPTIONS} />
          </Form.Item>
          <Form.Item name="customer_id" label="客户 (留空=全局)">
            <Select
              allowClear showSearch optionFilterProp="label"
              options={customers.map((c) => ({ label: c.customer_name, value: c.id }))}
            />
          </Form.Item>
          <Space.Compact block>
            <Form.Item name="threshold_value" label="阈值" style={{ flex: 2, marginRight: 8 }}>
              <InputNumber style={{ width: '100%' }} min={0} step={100} placeholder="数值" />
            </Form.Item>
            <Form.Item name="threshold_unit" label="单位" style={{ flex: 1 }}>
              <Input placeholder="CNY" />
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
              return overdue ? <Text style={{ color: '#ef4444' }}>{v}（超期）</Text> : v;
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
          borderRadius: 12, marginBottom: 16,
          background: 'linear-gradient(120deg, #fb7185 0%, #ef4444 50%, #f97316 100%)',
          color: 'white',
        }}
        styles={{ body: { padding: 28 } }}
      >
        <Space direction="vertical" size={4}>
          <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>ALERTS · 预警中心</Text>
          <Title level={2} style={{ color: 'white', margin: 0 }}>
            <AlertOutlined /> 预警与收款
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.85)' }}>
            云管预警 · 自定义规则 · 收款超期追踪
          </Text>
        </Space>
      </Card>

      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Tabs
          defaultActiveKey="cloudcost"
          items={[
            { key: 'cloudcost', label: '云管预警', children: <CloudcostTab /> },
            { key: 'my-rules', label: '我的规则', children: <MyRulesTab customers={customers} /> },
            { key: 'payments', label: '收款超期', children: <PaymentsTab customers={customers} /> },
          ]}
        />
      </Card>
    </div>
  );
}

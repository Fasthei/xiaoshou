import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Button, Card, Space, Table, Tag, Typography, Tabs, Drawer, Timeline, Empty,
  Popconfirm, Modal, Input, Descriptions, message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, HistoryOutlined, StopOutlined, EyeOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Allocation, Pagination } from '../types';
import { fmtTime } from '../utils/time';

interface CustomerLite { id: number; customer_name: string; customer_code?: string }
interface ResourceLite {
  id: number;
  resource_code?: string | null;
  cloud_provider?: string | null;
  account_name?: string | null;
}
interface SalesUserLite { id: number; name: string; email?: string | null }

const { Title, Text } = Typography;

const STATUS_COLOR: Record<string, string> = {
  PENDING: 'orange', ACTIVE: 'green', EXPIRED: 'default', CANCELLED: 'red',
};

interface HistoryEntry {
  id: number; field: string; old_value: string | null;
  new_value: string | null; reason: string | null; at: string;
  operator_casdoor_id: string | null;
}

const FIELD_LABEL: Record<string, string> = {
  cancel: '取消', allocated_quantity: '数量', unit_price: '单价',
  unit_cost: '单位成本', remark: '备注', delivery_status: '交付状态',
  allocation_status: '状态',
};

export default function Allocations() {
  const [rows, setRows] = useState<Allocation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState<'active' | 'cancelled'>('active');
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyAllocation, setHistoryAllocation] = useState<Allocation | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [cancelFor, setCancelFor] = useState<Allocation | null>(null);
  const [cancelReason, setCancelReason] = useState('');
  // 订单详情 (只读 Modal)
  const [orderDetail, setOrderDetail] = useState<Allocation | null>(null);
  // 客户 / 货源 / 销售 lookup —— 列里把 id 渲染成 名称
  const [customers, setCustomers] = useState<CustomerLite[]>([]);
  const [resources, setResources] = useState<ResourceLite[]>([]);
  const [salesUsers, setSalesUsers] = useState<SalesUserLite[]>([]);
  const customerMap = useMemo(() => new Map(customers.map((c) => [c.id, c])), [customers]);
  const resourceMap = useMemo(() => new Map(resources.map((r) => [r.id, r])), [resources]);
  const salesMap = useMemo(() => new Map(salesUsers.map((s) => [s.id, s])), [salesUsers]);
  const customerLabel = (id: number) => {
    const c = customerMap.get(id);
    return c ? `${c.customer_name}${c.customer_code ? ` · ${c.customer_code}` : ''}` : `#${id}`;
  };
  const resourceLabel = (id: number) => {
    const r = resourceMap.get(id);
    if (!r) return `#${id}`;
    const bits = [r.resource_code || `#${id}`, r.account_name || '-'];
    if (r.cloud_provider) bits.push(r.cloud_provider);
    return bits.join(' · ');
  };
  const salesLabel = (id?: number | null) => {
    if (id == null) return '—';
    const s = salesMap.get(id);
    return s ? `${s.name}${s.email ? ` · ${s.email}` : ''}` : `#${id}`;
  };

  const load = async () => {
    setLoading(true);
    try {
      const params: any = { page, page_size: pageSize };
      if (tab === 'cancelled') params.allocation_status = 'CANCELLED';
      const { data } = await api.get<Pagination<Allocation>>('/api/allocations', { params });
      let items = data.items;
      if (tab === 'active') items = items.filter((a: any) => a.allocation_status !== 'CANCELLED');
      setRows(items);
      setTotal(tab === 'active' ? items.length : data.total);
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '加载订单列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, pageSize, tab]);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/api/customers', { params: { page: 1, page_size: 100 } });
        const items: CustomerLite[] = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
        setCustomers(items.map((c) => ({ id: c.id, customer_name: c.customer_name, customer_code: c.customer_code })));
      } catch { /* ignore */ }
      try {
        const { data } = await api.get('/api/resources', { params: { page: 1, page_size: 100 } });
        const items: ResourceLite[] = Array.isArray(data?.items) ? data.items : Array.isArray(data) ? data : [];
        setResources(items);
      } catch { /* ignore */ }
      try {
        const { data } = await api.get<SalesUserLite[]>('/api/sales/users', { params: { active_only: false } });
        setSalesUsers(Array.isArray(data) ? data : []);
      } catch { /* ignore */ }
    })();
  }, []);

  const openHistory = async (a: Allocation) => {
    setHistoryAllocation(a);
    setHistoryOpen(true);
    setHistoryLoading(true);
    try {
      const { data } = await api.get<HistoryEntry[]>(`/api/allocations/${a.id}/history`);
      setHistory(data);
    } finally {
      setHistoryLoading(false);
    }
  };

  const cancelAllocation = async () => {
    if (!cancelFor) return;
    try {
      await api.post(`/api/allocations/${cancelFor.id}/cancel`, { reason: cancelReason || undefined });
      antdMessage.success('已取消订单，货源已退回池子');
      setCancelFor(null); setCancelReason('');
      load();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '取消订单失败');
    }
  };

  const baseCols: any[] = [
    { title: '订单编号', dataIndex: 'allocation_code', width: 180,
      render: (v: string, r: Allocation) => (
        <a onClick={() => setOrderDetail(r)}><code style={{ color: '#0078D4' }}>{v}</code></a>
      ) },
    { title: '客户', dataIndex: 'customer_id', width: 200, ellipsis: true,
      render: (v: number) => customerLabel(v) },
    { title: '货源', dataIndex: 'resource_id', width: 220, ellipsis: true,
      render: (v: number) => resourceLabel(v) },
    { title: '订单数量', dataIndex: 'allocated_quantity', width: 80 },
    { title: '总售价', dataIndex: 'total_price', width: 110 },
    { title: '毛利', dataIndex: 'profit_amount', width: 110 },
    {
      title: '毛利率(%)', dataIndex: 'profit_rate', width: 100,
      render: (v: any) => v != null ? `${v}%` : '-',
    },
    {
      title: '状态', dataIndex: 'allocation_status', width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '审批状态', dataIndex: 'approval_status', width: 100,
      render: (s: string) => {
        const color: Record<string, string> = { pending: 'orange', approved: 'green', rejected: 'red' };
        const label: Record<string, string> = { pending: '待审批', approved: '已审批', rejected: '已拒绝' };
        return s ? <Tag color={color[s] || 'default'}>{label[s] || s}</Tag> : '-';
      },
    },
    {
      title: '申请销售', dataIndex: 'allocated_by', width: 140, ellipsis: true,
      render: (v?: number | null) => salesLabel(v),
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170,
      render: (v?: string) => fmtTime(v) },
    {
      title: '操作', width: 240, fixed: 'right',
      render: (_: any, r: any) => (
        <Space size={0} wrap>
          <Button size="small" type="link" icon={<EyeOutlined />} onClick={() => setOrderDetail(r)}>
            详情
          </Button>
          <Button size="small" type="link" icon={<HistoryOutlined />} onClick={() => openHistory(r)}>
            历史
          </Button>
          {r.allocation_status !== 'CANCELLED' && (
            <Popconfirm
              title="取消这笔订单？"
              description="货源会退回池子, 并写入变更流水"
              onConfirm={() => { setCancelFor(r); setCancelReason(''); }}
              okText="确认"
            >
              <Button size="small" type="link" danger icon={<StopOutlined />}>取消</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <Card>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>订单管理</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>
      </Space>

      <Alert type="info" showIcon message="订单管理 · 在客户详情里创建订单，经主管审批后生效，在此查看所有进行中 / 已生效订单" style={{ marginBottom: 12 }} />

      <Tabs
        activeKey={tab}
        onChange={(k) => { setPage(1); setTab(k as any); }}
        items={[
          { key: 'active', label: '进行中 / 全部' },
          { key: 'cancelled', label: <Space>已取消 <Tag color="red">历史</Tag></Space> },
        ]}
      />

      <Table<Allocation>
        rowKey="id" loading={loading} columns={baseCols} dataSource={rows}
        scroll={{ x: 1400 }}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
      />

      {/* 历史流水 Drawer */}
      <Drawer
        title={
          historyAllocation
            ? <Space><HistoryOutlined /> {historyAllocation.allocation_code} 变更流水</Space>
            : '变更流水'
        }
        open={historyOpen} onClose={() => setHistoryOpen(false)} width={520}
      >
        {historyLoading ? (
          <Text type="secondary">加载中...</Text>
        ) : history.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该订单暂无变更记录" />
        ) : (
          <Timeline
            items={history.map((h) => ({
              color: h.field === 'cancel' ? 'red' : 'blue',
              children: (
                <Space direction="vertical" size={2}>
                  <Space>
                    <Tag color={h.field === 'cancel' ? 'red' : 'geekblue'}>
                      {FIELD_LABEL[h.field] || h.field}
                    </Tag>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {new Date(h.at).toLocaleString()}
                    </Text>
                  </Space>
                  <Text>
                    <Text type="secondary" delete>{h.old_value ?? '-'}</Text>
                    {' → '}
                    <Text strong>{h.new_value ?? '-'}</Text>
                  </Text>
                  {h.reason ? <Text italic>原因: {h.reason}</Text> : null}
                </Space>
              ),
            }))}
          />
        )}
      </Drawer>

      {/* 订单详情 Modal */}
      <Modal
        title={orderDetail ? `订单详情 — ${orderDetail.allocation_code}` : '订单详情'}
        open={!!orderDetail}
        onCancel={() => setOrderDetail(null)}
        width={780}
        destroyOnClose
        footer={<Button onClick={() => setOrderDetail(null)}>关闭</Button>}
      >
        {orderDetail && (() => {
          const d = orderDetail as any;
          const approval = (d.approval_status || 'pending') as 'pending' | 'approved' | 'rejected';
          const approvalMeta = {
            pending: { color: 'orange', label: '待审批' },
            approved: { color: 'green', label: '已通过' },
            rejected: { color: 'red', label: '已驳回' },
          }[approval] || { color: 'default', label: approval };
          return (
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="订单号" span={2}>
                <code style={{ color: '#0078D4' }}>{d.allocation_code}</code>
              </Descriptions.Item>
              <Descriptions.Item label="申请销售" span={2}>{salesLabel(d.allocated_by)}</Descriptions.Item>
              <Descriptions.Item label="客户" span={2}>{customerLabel(d.customer_id)}</Descriptions.Item>
              <Descriptions.Item label="货源" span={2}>{resourceLabel(d.resource_id)}</Descriptions.Item>
              <Descriptions.Item label="数量">{d.allocated_quantity ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={STATUS_COLOR[d.allocation_status] || 'default'}>{d.allocation_status || 'pending'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="折前单价">{d.unit_cost == null ? '—' : `¥ ${d.unit_cost}`}</Descriptions.Item>
              <Descriptions.Item label="折扣率">{d.discount_rate == null ? '—' : `${d.discount_rate} %`}</Descriptions.Item>
              <Descriptions.Item label="折后单价">{d.unit_price == null ? '—' : `¥ ${d.unit_price}`}</Descriptions.Item>
              <Descriptions.Item label="总成本">{d.total_cost == null ? '—' : `¥ ${d.total_cost}`}</Descriptions.Item>
              <Descriptions.Item label="总售价">{d.total_price == null ? '—' : `¥ ${d.total_price}`}</Descriptions.Item>
              <Descriptions.Item label="毛利">{d.profit_amount == null ? '—' : `¥ ${d.profit_amount}`}</Descriptions.Item>
              <Descriptions.Item label="毛利率" span={2}>{d.profit_rate == null ? '—' : `${d.profit_rate} %`}</Descriptions.Item>
              <Descriptions.Item label="终端用户标签" span={2}>{d.end_user_label || '—'}</Descriptions.Item>
              <Descriptions.Item label="备注" span={2}>{d.remark || '—'}</Descriptions.Item>
              <Descriptions.Item label="审批状态">
                <Tag color={approvalMeta.color}>{approvalMeta.label}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="审批备注">{d.approval_note || '—'}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{fmtTime(d.created_at)}</Descriptions.Item>
              <Descriptions.Item label="分配时间">{fmtTime(d.allocated_at)}</Descriptions.Item>
            </Descriptions>
          );
        })()}
      </Modal>

      {/* 取消原因 Modal */}
      <Modal
        title="取消订单"
        open={!!cancelFor}
        onOk={cancelAllocation}
        onCancel={() => { setCancelFor(null); setCancelReason(''); }}
        okText="确认取消"
        okButtonProps={{ danger: true }}
        destroyOnClose
      >
        <Text>取消 <Text strong>{cancelFor?.allocation_code}</Text> 后，货源 {cancelFor?.resource_id} 的已分配数量会减回 {cancelFor?.allocated_quantity}。</Text>
        <Input.TextArea
          style={{ marginTop: 12 }} rows={3}
          placeholder="原因 (可选), 会写入变更流水"
          value={cancelReason} onChange={(e) => setCancelReason(e.target.value)}
        />
      </Modal>
    </Card>
  );
}

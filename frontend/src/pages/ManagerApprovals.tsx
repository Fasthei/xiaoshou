import { useEffect, useMemo, useState } from 'react';
import {
  Button, Card, Descriptions, Empty, Form, Input, Modal, Space, Table, Tabs, Tag, Typography, message as antdMessage,
} from 'antd';
import {
  CheckOutlined, CloseOutlined, ReloadOutlined, AuditOutlined, NodeIndexOutlined,
  EyeOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Allocation } from '../types';
import { STAGE_META } from '../constants/stage';
import { fmtTime } from '../utils/time';
import { currencySymOf } from '../utils/currency';

const { Title, Text } = Typography;

interface CustomerLite { id: number; customer_name: string; customer_code?: string }
interface ResourceLite {
  id: number;
  resource_code?: string | null;
  cloud_provider?: string | null;
  account_name?: string | null;
}
interface SalesUserLite {
  id: number;
  name: string;
  email?: string | null;
}

interface StageRequest {
  id: number;
  customer_id: number;
  customer_name?: string;
  from_stage?: string;
  to_stage: string;
  requester_name?: string;
  reason?: string;
  status: string;
  created_at?: string;
}

export default function ManagerApprovals() {
  const [activeTab, setActiveTab] = useState('orders');

  // Orders tab
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Allocation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [backendMissing, setBackendMissing] = useState(false);

  // Stage requests tab
  const [srLoading, setSrLoading] = useState(false);
  const [srData, setSrData] = useState<StageRequest[]>([]);
  const [srMissing, setSrMissing] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectTarget, setRejectTarget] = useState<StageRequest | null>(null);
  const [rejectForm] = Form.useForm<{ comment: string }>();
  const [rejectLoading, setRejectLoading] = useState(false);

  // Order approve/reject
  const [orderRejectOpen, setOrderRejectOpen] = useState(false);
  const [orderRejectTarget, setOrderRejectTarget] = useState<Allocation | null>(null);
  const [orderRejectForm] = Form.useForm<{ approval_note: string }>();
  const [orderRejectLoading, setOrderRejectLoading] = useState(false);

  // Order detail view
  const [orderDetail, setOrderDetail] = useState<Allocation | null>(null);

  // Customer + resource + sales lookup (id → name) for showing readable info
  const [customers, setCustomers] = useState<CustomerLite[]>([]);
  const [resources, setResources] = useState<ResourceLite[]>([]);
  const [salesUsers, setSalesUsers] = useState<SalesUserLite[]>([]);
  const customerMap = useMemo(() => {
    const m = new Map<number, CustomerLite>();
    for (const c of customers) m.set(c.id, c);
    return m;
  }, [customers]);
  const resourceMap = useMemo(() => {
    const m = new Map<number, ResourceLite>();
    for (const r of resources) m.set(r.id, r);
    return m;
  }, [resources]);
  const salesMap = useMemo(() => {
    const m = new Map<number, SalesUserLite>();
    for (const s of salesUsers) m.set(s.id, s);
    return m;
  }, [salesUsers]);

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
  const salesLabel = (id: number | null | undefined) => {
    if (id == null) return '—';
    const s = salesMap.get(id);
    return s ? `${s.name}${s.email ? ` · ${s.email}` : ''}` : `#${id}`;
  };

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

  const loadOrders = async () => {
    setLoading(true);
    setBackendMissing(false);
    try {
      const { data } = await api.get('/api/allocations', {
        params: { approval_status: 'pending', page, page_size: pageSize },
      });
      if (Array.isArray(data)) {
        setData(data);
        setTotal(data.length);
      } else {
        setData(data?.items || []);
        setTotal(data?.total ?? (data?.items?.length || 0));
      }
    } catch (e: any) {
      if ([400, 404, 422].includes(e?.response?.status)) setBackendMissing(true);
      else antdMessage.error(e?.response?.data?.detail || '加载待审批订单失败');
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  const loadStageRequests = async () => {
    setSrLoading(true);
    setSrMissing(false);
    try {
      const { data } = await api.get('/api/stage-requests', { params: { status: 'pending' } });
      const items = Array.isArray(data) ? data : data?.items || [];
      setSrData(items);
    } catch (e: any) {
      if ([404, 422].includes(e?.response?.status)) setSrMissing(true);
      setSrData([]);
    } finally {
      setSrLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
    loadStageRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  const approveOrder = async (r: Allocation) => {
    try {
      await api.patch(`/api/allocations/${r.id}/approval`, {
        approval_status: 'approved',
        approval_note: null,
      });
      antdMessage.success(`订单 #${r.id} 已通过`);
      loadOrders();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '审批失败');
    }
  };

  const openOrderReject = (r: Allocation) => {
    setOrderRejectTarget(r);
    orderRejectForm.resetFields();
    setOrderRejectOpen(true);
  };

  const submitOrderReject = async () => {
    if (!orderRejectTarget) return;
    const v = await orderRejectForm.validateFields();
    setOrderRejectLoading(true);
    try {
      await api.patch(`/api/allocations/${orderRejectTarget.id}/approval`, {
        approval_status: 'rejected',
        approval_note: v.approval_note,
      });
      antdMessage.success(`订单 #${orderRejectTarget.id} 已驳回`);
      setOrderRejectOpen(false);
      loadOrders();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '驳回失败');
    } finally {
      setOrderRejectLoading(false);
    }
  };

  const approveStageRequest = async (id: number) => {
    try {
      await api.post(`/api/stage-requests/${id}/approve`);
      antdMessage.success('已通过');
      loadStageRequests();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '操作失败');
    }
  };

  const openReject = (r: StageRequest) => {
    setRejectTarget(r);
    rejectForm.resetFields();
    setRejectOpen(true);
  };

  const submitReject = async () => {
    if (!rejectTarget) return;
    const v = await rejectForm.validateFields();
    setRejectLoading(true);
    try {
      await api.post(`/api/stage-requests/${rejectTarget.id}/reject`, v);
      antdMessage.success('已驳回');
      setRejectOpen(false);
      loadStageRequests();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '操作失败');
    } finally {
      setRejectLoading(false);
    }
  };

  const orderColumns = [
    { title: '订单号', dataIndex: 'allocation_code', width: 180,
      render: (v: string, r: Allocation) => (
        <a onClick={() => setOrderDetail(r)} style={{ padding: 0 }}>
          <code style={{ color: '#0078D4' }}>{v}</code>
        </a>
      ) },
    { title: '客户', dataIndex: 'customer_id', width: 200, ellipsis: true,
      render: (v: number) => customerLabel(v) },
    { title: '货源', dataIndex: 'resource_id', width: 220, ellipsis: true,
      render: (v: number) => resourceLabel(v) },
    { title: '数量', dataIndex: 'allocated_quantity', width: 80 },
    { title: '单价', dataIndex: 'unit_price', width: 110,
      render: (v: any, r: Allocation) => v == null ? '—' : `${currencySymOf(r)}${v}` },
    { title: '总金额', dataIndex: 'total_price', width: 130,
      render: (v: any, r: Allocation) => v == null ? '—' : `${currencySymOf(r)}${v}` },
    { title: '状态', dataIndex: 'allocation_status', width: 90,
      render: (s: string) => <Tag color="orange">{s || 'pending'}</Tag> },
    { title: '申请销售', dataIndex: 'allocated_by', width: 160, ellipsis: true,
      render: (v: number | null | undefined) => salesLabel(v) },
    { title: '创建时间', dataIndex: 'created_at', width: 160,
      render: (v: string | undefined) => fmtTime(v) },
    {
      title: '操作', width: 230, fixed: 'right' as const,
      render: (_: unknown, r: Allocation) => (
        <Space size={0} wrap>
          <Button
            size="small" type="link" icon={<EyeOutlined />}
            onClick={() => setOrderDetail(r)}
          >详情</Button>
          <Button
            size="small" type="primary" icon={<CheckOutlined />}
            onClick={() => approveOrder(r)}
          >通过</Button>
          <Button
            size="small" danger icon={<CloseOutlined />}
            onClick={() => openOrderReject(r)}
          >驳回</Button>
        </Space>
      ),
    },
  ];

  const stageRequestColumns = [
    { title: '客户', dataIndex: 'customer_name', ellipsis: true,
      render: (v: string, r: StageRequest) => v || `#${r.customer_id}` },
    {
      title: 'Stage 变更', width: 200,
      render: (_: unknown, r: StageRequest) => {
        const fromMeta = r.from_stage ? STAGE_META[r.from_stage] : null;
        const toMeta = r.to_stage ? STAGE_META[r.to_stage] : null;
        return (
          <Space size={4}>
            {fromMeta ? <Tag color={fromMeta.color}>{fromMeta.emoji} {fromMeta.label}</Tag> : r.from_stage ? <Tag>{r.from_stage}</Tag> : <Tag color="default">—</Tag>}
            <Text type="secondary">→</Text>
            {toMeta ? <Tag color={toMeta.color}>{toMeta.emoji} {toMeta.label}</Tag> : <Tag>{r.to_stage}</Tag>}
          </Space>
        );
      },
    },
    { title: '申请人', dataIndex: 'requester_name', width: 100 },
    { title: '原因', dataIndex: 'reason', ellipsis: true },
    { title: '申请时间', dataIndex: 'created_at', width: 170,
      render: (v: string | undefined) => fmtTime(v) },
    {
      title: '操作', width: 160, fixed: 'right' as const,
      render: (_: unknown, r: StageRequest) => (
        <Space size={4}>
          <Button
            size="small" type="primary" icon={<CheckOutlined />}
            onClick={() => approveStageRequest(r.id)}
          >通过</Button>
          <Button
            size="small" danger icon={<CloseOutlined />}
            onClick={() => openReject(r)}
          >驳回</Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-fade">
      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
          <Space direction="vertical" size={0}>
            <Title level={4} style={{ margin: 0 }}>
              <AuditOutlined style={{ marginRight: 8 }} />
              审批中心
            </Title>
            <Text type="secondary">订单审批 + 客户 Stage 变更审批</Text>
          </Space>
          <Button icon={<ReloadOutlined />} onClick={() => { loadOrders(); loadStageRequests(); }}>刷新</Button>
        </Space>

        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            {
              key: 'orders',
              label: <Space><AuditOutlined />待审批订单</Space>,
              children: (
                <Table<Allocation>
                  rowKey="id"
                  loading={loading}
                  columns={orderColumns}
                  dataSource={data}
                  scroll={{ x: 1200 }}
                  pagination={{
                    current: page, pageSize, total,
                    showSizeChanger: true, showTotal: (t) => `共 ${t} 条`,
                    onChange: (p, ps) => { setPage(p); setPageSize(ps); },
                  }}
                  locale={{
                    emptyText: backendMissing ? (
                      <Empty
                        description={<>后端 <code>GET /api/allocations?approval_status=pending</code> 尚未落地</>}
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                      />
                    ) : (
                      <Empty description="暂无待审批订单" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ),
                  }}
                />
              ),
            },
            {
              key: 'stage-requests',
              label: (
                <Space>
                  <NodeIndexOutlined />
                  客户 Stage 变更审批
                  {srData.length > 0 && <Tag color="red">{srData.length}</Tag>}
                </Space>
              ),
              children: (
                <Table<StageRequest>
                  rowKey="id"
                  loading={srLoading}
                  columns={stageRequestColumns}
                  dataSource={srData}
                  scroll={{ x: 900 }}
                  pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
                  locale={{
                    emptyText: srMissing ? (
                      <Empty
                        description={<>后端 <code>GET /api/stage-requests?status=pending</code> 待上线</>}
                        image={Empty.PRESENTED_IMAGE_SIMPLE}
                      />
                    ) : (
                      <Empty description="暂无待审批的 stage 变更" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    ),
                  }}
                />
              ),
            },
          ]}
        />
      </Card>

      {/* Order Reject Modal */}
      <Modal
        title={`驳回订单 — ${orderRejectTarget?.allocation_code || ''}`}
        open={orderRejectOpen}
        onOk={submitOrderReject}
        onCancel={() => setOrderRejectOpen(false)}
        confirmLoading={orderRejectLoading}
        destroyOnClose
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
      >
        <Form form={orderRejectForm} layout="vertical">
          <Form.Item name="approval_note" label="驳回原因" rules={[{ required: true, message: '请填写驳回原因' }]}>
            <Input.TextArea rows={3} placeholder="说明驳回原因…" />
          </Form.Item>
        </Form>
      </Modal>

      {/* Order Detail Modal */}
      <Modal
        title={orderDetail ? `订单详情 — ${orderDetail.allocation_code}` : '订单详情'}
        open={!!orderDetail}
        onCancel={() => setOrderDetail(null)}
        width={780}
        destroyOnClose
        footer={
          orderDetail ? (
            <Space>
              <Button onClick={() => setOrderDetail(null)}>关闭</Button>
              <Button
                danger icon={<CloseOutlined />}
                onClick={() => { const t = orderDetail; setOrderDetail(null); openOrderReject(t); }}
              >驳回</Button>
              <Button
                type="primary" icon={<CheckOutlined />}
                onClick={() => { const t = orderDetail; setOrderDetail(null); approveOrder(t); }}
              >通过</Button>
            </Space>
          ) : null
        }
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
                <Tag color="orange">{d.allocation_status || 'pending'}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="货币">{d.currency || 'CNY'}</Descriptions.Item>
              <Descriptions.Item label="折扣率">{d.discount_rate == null ? '—' : `${d.discount_rate} %`}</Descriptions.Item>
              <Descriptions.Item label="折前单价">{d.unit_cost == null ? '—' : `${currencySymOf(d)} ${d.unit_cost}`}</Descriptions.Item>
              <Descriptions.Item label="折后单价">{d.unit_price == null ? '—' : `${currencySymOf(d)} ${d.unit_price}`}</Descriptions.Item>
              <Descriptions.Item label="总成本">{d.total_cost == null ? '—' : `${currencySymOf(d)} ${d.total_cost}`}</Descriptions.Item>
              <Descriptions.Item label="总售价">{d.total_price == null ? '—' : `${currencySymOf(d)} ${d.total_price}`}</Descriptions.Item>
              <Descriptions.Item label="毛利" span={2}>{d.profit_amount == null ? '—' : `${currencySymOf(d)} ${d.profit_amount}`}</Descriptions.Item>
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

      {/* Stage Request Reject Modal */}
      <Modal
        title={`驳回 Stage 变更 — ${rejectTarget?.customer_name || ''}`}
        open={rejectOpen}
        onOk={submitReject}
        onCancel={() => setRejectOpen(false)}
        confirmLoading={rejectLoading}
        destroyOnClose
        okText="确认驳回"
        okButtonProps={{ danger: true }}
        cancelText="取消"
      >
        <Form form={rejectForm} layout="vertical">
          <Form.Item name="comment" label="驳回原因" rules={[{ required: true, message: '请填写驳回原因' }]}>
            <Input.TextArea rows={3} placeholder="说明驳回原因…" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

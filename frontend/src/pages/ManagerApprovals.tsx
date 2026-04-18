import { useEffect, useState } from 'react';
import {
  Button, Card, Empty, Form, Input, Modal, Space, Table, Tabs, Tag, Typography, message as antdMessage,
} from 'antd';
import {
  CheckOutlined, CloseOutlined, ReloadOutlined, AuditOutlined, NodeIndexOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Allocation } from '../types';
import { STAGE_META } from '../constants/stage';

const { Title, Text } = Typography;

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
      render: (v: string) => <code style={{ color: '#4f46e5' }}>{v}</code> },
    { title: '客户 ID', dataIndex: 'customer_id', width: 100 },
    { title: '货源 ID', dataIndex: 'resource_id', width: 100 },
    { title: '数量', dataIndex: 'allocated_quantity', width: 100 },
    { title: '单价', dataIndex: 'unit_price', width: 120,
      render: (v: any) => v == null ? '—' : `¥${v}` },
    { title: '总金额', dataIndex: 'total_price', width: 140,
      render: (v: any) => v == null ? '—' : `¥${v}` },
    { title: '状态', dataIndex: 'allocation_status', width: 110,
      render: (s: string) => <Tag color="orange">{s || 'pending'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', width: 170,
      render: (v: string | undefined) => v ? v.replace('T', ' ').slice(0, 19) : '—' },
    {
      title: '操作', width: 200, fixed: 'right' as const,
      render: (_: unknown, r: Allocation) => (
        <Space size={4}>
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
      render: (v: string | undefined) => v ? v.replace('T', ' ').slice(0, 19) : '—' },
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

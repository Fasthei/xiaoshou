import { useEffect, useState } from 'react';
import {
  Alert, Button, Card, Space, Table, Tag, Typography, Tabs, Drawer, Timeline, Empty,
  Popconfirm, Modal, Input, message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, HistoryOutlined, StopOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Allocation, Pagination } from '../types';

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
    { title: '订单编号', dataIndex: 'allocation_code', width: 180 },
    { title: '客户 ID', dataIndex: 'customer_id', width: 80 },
    { title: '货源 ID', dataIndex: 'resource_id', width: 80 },
    { title: '订单数量', dataIndex: 'allocated_quantity', width: 90 },
    { title: '总售价', dataIndex: 'total_price', width: 110 },
    { title: '毛利', dataIndex: 'profit_amount', width: 110 },
    {
      title: '毛利率(%)', dataIndex: 'profit_rate', width: 100,
      render: (v: any) => v != null ? `${v}%` : '-',
    },
    {
      title: '状态', dataIndex: 'allocation_status', width: 110,
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
      title: '发起人', dataIndex: 'allocated_by', width: 90,
      render: (v: any) => v ?? '-',
    },
    {
      title: '审批人', dataIndex: 'approver_id', width: 90,
      render: (v: any) => v ?? '-',
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
    {
      title: '操作', width: 200, fixed: 'right',
      render: (_: any, r: any) => (
        <Space size={4}>
          <Button size="small" icon={<HistoryOutlined />} onClick={() => openHistory(r)}>历史</Button>
          {r.allocation_status !== 'CANCELLED' && (
            <Popconfirm
              title="取消这笔订单？"
              description="货源会退回池子, 并写入变更流水"
              onConfirm={() => { setCancelFor(r); setCancelReason(''); }}
              okText="确认"
            >
              <Button size="small" danger icon={<StopOutlined />}>取消</Button>
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

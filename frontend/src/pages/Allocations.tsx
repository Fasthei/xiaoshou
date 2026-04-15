import { useEffect, useState } from 'react';
import { Button, Card, Space, Table, Tag, Typography } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { Allocation, Pagination } from '../types';
import AllocationCreateModal from '../components/AllocationCreateModal';

const { Title } = Typography;

const STATUS_COLOR: Record<string, string> = {
  PENDING: 'orange', ACTIVE: 'green', EXPIRED: 'default', CANCELLED: 'red',
};

export default function Allocations() {
  const [rows, setRows] = useState<Allocation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Pagination<Allocation>>('/api/allocations', {
        params: { page, page_size: pageSize },
      });
      setRows(data.items); setTotal(data.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, pageSize]);

  const columns = [
    { title: '分配编号', dataIndex: 'allocation_code', width: 170 },
    { title: '客户 ID', dataIndex: 'customer_id', width: 90 },
    { title: '货源 ID', dataIndex: 'resource_id', width: 90 },
    { title: '分配数量', dataIndex: 'allocated_quantity', width: 90 },
    { title: '总成本', dataIndex: 'total_cost', width: 110 },
    { title: '总售价', dataIndex: 'total_price', width: 110 },
    { title: '毛利', dataIndex: 'profit_amount', width: 110 },
    {
      title: '毛利率(%)', dataIndex: 'profit_rate', width: 110,
      render: (v: string | number | null) => v != null ? `${v}%` : '-',
    },
    {
      title: '状态', dataIndex: 'allocation_status', width: 120,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: '创建时间', dataIndex: 'created_at', width: 170 },
  ];

  return (
    <Card>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>分配管理</Title>
        <Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>
            新建分配
          </Button>
        </Space>
      </Space>
      <AllocationCreateModal
        open={createOpen} onClose={() => setCreateOpen(false)} onCreated={load}
      />
      <Table<Allocation>
        rowKey="id" loading={loading} columns={columns} dataSource={rows}
        scroll={{ x: 1200 }}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
      />
    </Card>
  );
}

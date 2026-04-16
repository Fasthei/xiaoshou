import { useEffect, useState } from 'react';
import {
  Button, Card, Empty, Space, Table, Tag, Typography, message as antdMessage,
} from 'antd';
import {
  CheckOutlined, CloseOutlined, ReloadOutlined, AuditOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Allocation } from '../types';

const { Title, Text } = Typography;

export default function ManagerApprovals() {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<Allocation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [backendMissing, setBackendMissing] = useState(false);

  const load = async () => {
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
      // 后端 Task #3 未落地 approval_status 过滤器时降级
      if ([400, 404, 422].includes(e?.response?.status)) {
        setBackendMissing(true);
      } else {
        antdMessage.error(e?.response?.data?.detail || '加载待审批订单失败');
      }
      setData([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize]);

  const columns = [
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
            onClick={() => antdMessage.info(
              `pending backend — 通过订单 #${r.id} 待接入 POST /api/allocations/${r.id}/approve`,
            )}
          >
            通过
          </Button>
          <Button
            size="small" danger icon={<CloseOutlined />}
            onClick={() => antdMessage.info(
              `pending backend — 驳回订单 #${r.id} 待接入 POST /api/allocations/${r.id}/reject`,
            )}
          >
            驳回
          </Button>
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
              待审批订单
            </Title>
            <Text type="secondary">
              所有 approval_status = pending 的订单；销售主管审批后生效。
            </Text>
          </Space>
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
        </Space>

        <Table<Allocation>
          rowKey="id"
          loading={loading}
          columns={columns}
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
                description={
                  <>
                    后端 <code>GET /api/allocations?approval_status=pending</code>
                    {' '}尚未落地（Task #3 进行中）
                  </>
                }
                image={Empty.PRESENTED_IMAGE_SIMPLE}
              />
            ) : (
              <Empty description="暂无待审批订单" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            ),
          }}
        />
      </Card>
    </div>
  );
}

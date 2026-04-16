import { useEffect, useState } from 'react';
import {
  Card, Col, Row, Statistic, Skeleton, Space, Typography, Tag, Table, Button,
  Empty, Progress, Alert, message as antdMessage,
} from 'antd';
import {
  RiseOutlined, FallOutlined, DollarOutlined, FundProjectionScreenOutlined,
  CheckOutlined, CloseOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api } from '../api/axios';
import type { Allocation } from '../types';

const { Title, Text } = Typography;

interface ManagerKpis {
  opportunities: number;          // 商业机会 (本月新增潜在客户 / 进行中的订单等, 后端定义)
  conversion_rate: number;        // 转化率 (近 90 天, 0-1)
  growth_rate: number;            // 增长率 (本月 GMV / 上月 GMV - 1)
  payment_rate: number;           // 回款率 (paid / confirmed, 0-1)
}

interface SalesPerf {
  id: number;
  name: string;
  ytd_gmv: number;
  target_gmv: number | null;
  progress_pct: number;
  customer_count: number;
}

function currentYearMonth(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${d.getFullYear()}-${mm}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

export default function ManagerDashboard() {
  const [month] = useState(currentYearMonth());
  const [kpis, setKpis] = useState<ManagerKpis | null>(null);
  const [kpisLoading, setKpisLoading] = useState(true);
  const [kpisMissing, setKpisMissing] = useState(false);

  const [pendingApprovals, setPendingApprovals] = useState<Allocation[]>([]);
  const [approvalsLoading, setApprovalsLoading] = useState(true);

  const [salesPerf, setSalesPerf] = useState<SalesPerf[]>([]);
  const [perfLoading, setPerfLoading] = useState(true);
  const [perfMissing, setPerfMissing] = useState(false);

  const loadKpis = async () => {
    setKpisLoading(true);
    setKpisMissing(false);
    try {
      const { data } = await api.get<ManagerKpis>('/api/manager/kpis', { params: { month } });
      setKpis(data);
    } catch (e: any) {
      if (e?.response?.status === 404) {
        setKpisMissing(true);
      } else {
        antdMessage.error(e?.response?.data?.detail || '加载 KPI 失败');
      }
      setKpis(null);
    } finally {
      setKpisLoading(false);
    }
  };

  const loadPendingApprovals = async () => {
    setApprovalsLoading(true);
    try {
      const { data } = await api.get('/api/allocations', {
        params: { approval_status: 'pending', page: 1, page_size: 10 },
      });
      // 兼容两种返回形状: Pagination<Allocation> 或直接数组
      const items: Allocation[] = Array.isArray(data) ? data : data?.items || [];
      setPendingApprovals(items);
    } catch (e: any) {
      // 后端 Task #3 还没落地 approval_status filter 时, 这里会 400/404 — 静默降级为空列表
      setPendingApprovals([]);
    } finally {
      setApprovalsLoading(false);
    }
  };

  const loadSalesPerf = async () => {
    setPerfLoading(true);
    setPerfMissing(false);
    try {
      const { data } = await api.get<SalesPerf[] | { items: SalesPerf[] }>(
        '/api/manager/sales-performance', { params: { month } },
      );
      const items: SalesPerf[] = Array.isArray(data) ? data : (data as any)?.items || [];
      setSalesPerf(items);
    } catch (e: any) {
      if (e?.response?.status === 404) {
        setPerfMissing(true);
      }
      setSalesPerf([]);
    } finally {
      setPerfLoading(false);
    }
  };

  useEffect(() => {
    loadKpis();
    loadPendingApprovals();
    loadSalesPerf();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const approvalCols = [
    { title: '订单号', dataIndex: 'allocation_code', width: 160,
      render: (v: string) => <code style={{ color: '#4f46e5' }}>{v}</code> },
    { title: '客户 ID', dataIndex: 'customer_id', width: 100 },
    { title: '货源 ID', dataIndex: 'resource_id', width: 100 },
    { title: '数量', dataIndex: 'allocated_quantity', width: 100 },
    { title: '金额', dataIndex: 'total_price', width: 120,
      render: (v: any) => v == null ? '—' : `¥${v}` },
    { title: '状态', dataIndex: 'allocation_status', width: 100,
      render: (s: string) => <Tag color="orange">{s || 'pending'}</Tag> },
    {
      title: '操作', width: 180, fixed: 'right' as const,
      render: (_: unknown, r: Allocation) => (
        <Space size={4}>
          <Button
            size="small" type="primary" icon={<CheckOutlined />}
            onClick={() => antdMessage.info(`pending backend — 通过订单 #${r.id} 待接入 POST /api/allocations/${r.id}/approve`)}
          >
            通过
          </Button>
          <Button
            size="small" danger icon={<CloseOutlined />}
            onClick={() => antdMessage.info(`pending backend — 驳回订单 #${r.id} 待接入 POST /api/allocations/${r.id}/reject`)}
          >
            驳回
          </Button>
        </Space>
      ),
    },
  ];

  const perfCols = [
    { title: '销售', dataIndex: 'name', width: 140,
      render: (v: string) => <Tag color="geekblue">{v}</Tag> },
    { title: '客户数', dataIndex: 'customer_count', width: 100 },
    { title: 'YTD 业绩', dataIndex: 'ytd_gmv', width: 140,
      render: (v: number) => v == null ? '—' : `¥${Number(v).toLocaleString()}` },
    { title: '年度目标', dataIndex: 'target_gmv', width: 140,
      render: (v: number | null) => v == null ? <Text type="secondary">未设置</Text> : `¥${Number(v).toLocaleString()}` },
    { title: '达成进度', dataIndex: 'progress_pct', width: 200,
      render: (v: number, r: SalesPerf) =>
        r.target_gmv == null ? <Text type="secondary">—</Text> : (
          <Progress
            percent={Math.min(100, Math.max(0, Math.round(v)))}
            size="small"
            status={v >= 100 ? 'success' : v >= 70 ? 'active' : 'normal'}
          />
        ),
    },
  ];

  return (
    <div className="page-fade">
      {/* Hero banner */}
      <Card
        bordered={false}
        style={{
          borderRadius: 16,
          marginBottom: 16,
          background: 'linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #ec4899 100%)',
          color: '#fff',
        }}
        bodyStyle={{ padding: 24 }}
      >
        <Space direction="vertical" size={4} style={{ color: '#fff' }}>
          <Title level={3} style={{ color: '#fff', margin: 0 }}>
            <FundProjectionScreenOutlined style={{ marginRight: 8 }} />
            销售主管 · 全景视图
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.9)' }}>
            {month} · 商业机会 / 转化率 / 增长率 / 回款率 · 团队业绩与待审批订单
          </Text>
        </Space>
      </Card>

      {kpisMissing && (
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="KPI 接口待上线"
          description={
            <>
              后端 <code>GET /api/manager/kpis?month=YYYY-MM</code> 尚未实现。KPI 卡片显示占位。
            </>
          }
        />
      )}

      {/* 4 KPI cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? (
              <Skeleton active paragraph={{ rows: 1 }} />
            ) : (
              <Statistic
                title={<Space><ThunderboltOutlined /> 商业机会 (本月)</Space>}
                value={kpis?.opportunities ?? '—'}
                valueStyle={{ color: '#4f46e5' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? (
              <Skeleton active paragraph={{ rows: 1 }} />
            ) : (
              <Statistic
                title="转化率 (近 90 天)"
                value={fmtPct(kpis?.conversion_rate)}
                valueStyle={{ color: '#0ea5e9' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? (
              <Skeleton active paragraph={{ rows: 1 }} />
            ) : (
              <Statistic
                title="增长率 (本月 vs 上月)"
                value={fmtPct(kpis?.growth_rate)}
                valueStyle={{ color: (kpis?.growth_rate ?? 0) >= 0 ? '#22c55e' : '#ef4444' }}
                prefix={(kpis?.growth_rate ?? 0) >= 0 ? <RiseOutlined /> : <FallOutlined />}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? (
              <Skeleton active paragraph={{ rows: 1 }} />
            ) : (
              <Statistic
                title="回款率 (paid / confirmed)"
                value={fmtPct(kpis?.payment_rate)}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#f59e0b' }}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* 待审批订单 */}
      <Card
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
        title="待审批订单"
        extra={<Link to="/manager/approvals">查看全部 →</Link>}
      >
        <Table<Allocation>
          rowKey="id"
          loading={approvalsLoading}
          columns={approvalCols}
          dataSource={pendingApprovals}
          scroll={{ x: 900 }}
          pagination={false}
          size="small"
          locale={{
            emptyText: <Empty description="暂无待审批订单" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
          }}
        />
      </Card>

      {/* 销售团队业绩 */}
      <Card
        bordered={false}
        style={{ borderRadius: 12 }}
        title="销售团队业绩"
        extra={
          perfMissing
            ? <Tag color="orange">接口待上线</Tag>
            : <Link to="/sales-team">团队管理 →</Link>
        }
      >
        {perfMissing ? (
          <Alert
            type="info"
            showIcon
            message="后端 GET /api/manager/sales-performance 尚未实现"
            description="接口就位后将展示每位销售的 YTD 业绩、年度目标与达成进度。"
          />
        ) : (
          <Table<SalesPerf>
            rowKey="id"
            loading={perfLoading}
            columns={perfCols}
            dataSource={salesPerf}
            scroll={{ x: 780 }}
            pagination={false}
            size="small"
            locale={{
              emptyText: <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />,
            }}
          />
        )}
      </Card>
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import {
  Card, Table, Tag, Typography, Space, DatePicker, Button, Statistic,
  Row, Col, Empty, Alert, Modal,
  message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, DollarOutlined, DownloadOutlined, CalculatorOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { api } from '../api/axios';
import DiscountCalculatorDrawer from '../components/DiscountCalculatorDrawer';

const { Title, Text } = Typography;

interface ResourceBill {
  resource_id: number;
  resource_code: string | null;
  cloud_provider: string | null;
  account_name: string | null;
  cost: number;
}

interface CustomerBill {
  customer_id: number;
  customer_name: string;
  customer_code: string | null;
  month: string;
  total_cost: number;
  resource_count: number;
  resources: ResourceBill[];
}

interface DayItem {
  date: string;
  total_cost: number;
  total_usage: number;
  record_count: number;
}

export default function Bills() {
  const [month, setMonth] = useState<Dayjs | null>(dayjs());
  const [loading, setLoading] = useState(false);
  const [rows, setRows] = useState<CustomerBill[]>([]);
  const [errMsg, setErrMsg] = useState<string | null>(null);
  const [calcOpen, setCalcOpen] = useState(false);
  const [exporting, setExporting] = useState(false);

  // 下钻状态: expandedRowKeys 控制客户行展开 → 子表 (按货源)
  // 再点某货源 → 弹出 drawer 级别的按日明细
  const [dayDrill, setDayDrill] = useState<{
    customer_id: number; customer_name: string; items: DayItem[]; loading: boolean;
  } | null>(null);

  const loadData = async () => {
    const m = month?.format('YYYY-MM');
    if (!m) return;
    setLoading(true);
    setErrMsg(null);
    try {
      const { data } = await api.get<CustomerBill[]>('/api/bills/by-customer', {
        params: { month: m },
      });
      setRows(Array.isArray(data) ? data : []);
    } catch (e: any) {
      setErrMsg(e?.response?.data?.detail || e?.message || '加载失败');
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadData(); /* eslint-disable-next-line */ }, [month]);

  const loadDayDrill = async (customer_id: number, customer_name: string) => {
    const m = month?.format('YYYY-MM');
    if (!m) return;
    setDayDrill({ customer_id, customer_name, items: [], loading: true });
    try {
      const { data } = await api.get(
        `/api/bills/by-customer/${customer_id}`,
        { params: { month: m, granularity: 'day' } },
      );
      setDayDrill({
        customer_id, customer_name,
        items: data?.items || [], loading: false,
      });
    } catch (e: any) {
      antdMessage.error('加载日明细失败: ' + (e?.message || ''));
      setDayDrill(null);
    }
  };

  const doExport = async (m: string) => {
    setExporting(true);
    try {
      const token = localStorage.getItem('token') || sessionStorage.getItem('token') || '';
      const resp = await fetch(`/api/bills/export?month=${encodeURIComponent(m)}&format=csv`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      });
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

  const handleExport = () => {
    const m = month?.format('YYYY-MM');
    if (!m) {
      antdMessage.warning('请先选择月份');
      return;
    }
    Modal.info({
      title: '导出账单 CSV',
      content: (
        <div>
          <p>导出 <strong>{m}</strong> 账单，包含以下列：</p>
          <ul style={{ paddingLeft: 20, margin: '8px 0' }}>
            <li>月份 / 客户名</li>
            <li>货源厂商 / 货源账号</li>
            <li>折前金额（cloudcost 原价）</li>
            <li>折扣率</li>
            <li>折后金额</li>
            <li>毛利</li>
          </ul>
          <p style={{ color: '#888', fontSize: 12 }}>
            如 cc_bill 数据未同步，CSV 将为空行（后端日志有告警）。
          </p>
        </div>
      ),
      okText: '确认导出',
      onOk: () => doExport(m),
    });
  };

  const totalAll = useMemo(
    () => rows.reduce((s, r) => s + Number(r.total_cost || 0), 0),
    [rows],
  );
  const customerCount = rows.length;
  const resourceLinkCount = useMemo(
    () => rows.reduce((s, r) => s + r.resource_count, 0),
    [rows],
  );

  const customerColumns = [
    { title: '客户名称', dataIndex: 'customer_name', width: 220,
      render: (v: string, r: CustomerBill) => (
        <Space>
          <Text strong>{v}</Text>
          {r.customer_code && <Tag color="default">{r.customer_code}</Tag>}
        </Space>
      ),
    },
    { title: '关联货源数', dataIndex: 'resource_count', width: 120,
      render: (v: number) => <Tag color={v > 0 ? 'blue' : 'default'}>{v}</Tag> },
    { title: '本月总费用', dataIndex: 'total_cost', width: 160,
      render: (v: number) => <Text strong style={{ color: '#ec4899' }}>¥{Number(v).toFixed(2)}</Text> },
    { title: '操作', width: 140, render: (_: any, r: CustomerBill) => (
      <Button size="small" type="link"
        onClick={() => loadDayDrill(r.customer_id, r.customer_name)}>
        按日明细
      </Button>
    )},
  ];

  const renderResourceSubTable = (row: CustomerBill) => (
    <Table<ResourceBill>
      rowKey="resource_id"
      size="small"
      pagination={false}
      dataSource={row.resources}
      locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="该客户暂无关联货源" /> }}
      columns={[
        { title: '货源编号', dataIndex: 'resource_code', width: 180 },
        { title: '云厂商', dataIndex: 'cloud_provider', width: 100,
          render: (v: string | null) => v ? <Tag color="geekblue">{v}</Tag> : '-' },
        { title: '账号', dataIndex: 'account_name', width: 220,
          render: (v: string | null) => v || '-' },
        { title: '本月费用', dataIndex: 'cost', width: 140,
          render: (v: number) => <Text strong>¥{Number(v).toFixed(2)}</Text> },
      ]}
    />
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
            <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>BILLS · 本地聚合</Text>
            <Title level={2} style={{ color: 'white', margin: '4px 0 0' }}>
              <DollarOutlined /> 账单中心
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.8)' }}>
              按客户本地关联货源聚合 (customer_resource) · 不再直接展示云管原始费用
            </Text>
          </Col>
          <Col xs={24} md={4}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>客户数</span>}
              value={customerCount}
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
          <Col xs={24} md={4}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>关联货源</span>}
              value={resourceLinkCount}
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
          <Col xs={24} md={4}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>本月总金额</span>}
              value={totalAll} precision={2} prefix="¥"
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
        </Row>
      </Card>

      <Card
        bordered={false}
        style={{ borderRadius: 12 }}
        title={<Title level={4} style={{ margin: 0 }}>月度账单</Title>}
        extra={
          <Space wrap>
            <DatePicker picker="month" value={month} onChange={setMonth} allowClear={false} />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            <Button icon={<CalculatorOutlined />} onClick={() => setCalcOpen(true)}>
              折扣计算器
            </Button>
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
              导出 CSV
            </Button>
          </Space>
        }
      >
        {errMsg && (
          <Alert type="error" showIcon style={{ marginBottom: 12 }}
            message="加载失败" description={errMsg} />
        )}
        {rows.length === 0 && !loading && !errMsg && (
          <Alert
            type="info" showIcon style={{ marginBottom: 12 }}
            message="本月暂无账单数据"
            description="确认客户详情「关联货源」已勾选, 且云管账单已同步到本地 cc_bill 表。"
          />
        )}
        <Table<CustomerBill>
          rowKey="customer_id"
          loading={loading}
          dataSource={rows}
          pagination={{ pageSize: 20, showSizeChanger: true }}
          columns={customerColumns}
          expandable={{
            expandedRowRender: renderResourceSubTable,
            rowExpandable: (r) => r.resources.length > 0,
          }}
        />
      </Card>

      {/* 按日明细 - 简易内嵌展示 */}
      {dayDrill && (
        <Card
          bordered={false}
          style={{ borderRadius: 12, marginTop: 16 }}
          title={
            <Space>
              <Text strong>按日明细 · {dayDrill.customer_name}</Text>
              <Text type="secondary">{month?.format('YYYY-MM')}</Text>
            </Space>
          }
          extra={<Button size="small" onClick={() => setDayDrill(null)}>关闭</Button>}
        >
          <Table<DayItem>
            rowKey="date"
            size="small"
            loading={dayDrill.loading}
            dataSource={dayDrill.items}
            pagination={{ pageSize: 31 }}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
              description="当月无每日用量数据 (cc_usage 可能为空)" /> }}
            columns={[
              { title: '日期', dataIndex: 'date', width: 140 },
              { title: '当日费用', dataIndex: 'total_cost', width: 140,
                render: (v: number) => <Text strong>¥{Number(v).toFixed(2)}</Text> },
              { title: '当日用量', dataIndex: 'total_usage', width: 140,
                render: (v: number) => Number(v).toFixed(4) },
              { title: '明细条数', dataIndex: 'record_count', width: 120 },
            ]}
          />
        </Card>
      )}

      <DiscountCalculatorDrawer open={calcOpen} onClose={() => setCalcOpen(false)} />
    </div>
  );
}

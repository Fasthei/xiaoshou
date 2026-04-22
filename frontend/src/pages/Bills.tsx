import { useEffect, useMemo, useState } from 'react';
import {
  Card, Table, Tag, Typography, Space, DatePicker, Button, Statistic,
  Row, Col, Empty, Alert, Modal, Tabs, Dropdown,
  message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, DollarOutlined, DownloadOutlined, CalculatorOutlined,
  BarChartOutlined, CloudSyncOutlined, DownOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { api, getCurrentRoles } from '../api/axios';
import DiscountCalculatorDrawer from '../components/DiscountCalculatorDrawer';
import Reports from './Reports';

const { Title, Text } = Typography;

interface ResourceBill {
  resource_id: number;
  resource_code: string | null;
  cloud_provider: string | null;
  account_name: string | null;
  identifier_field: string | null;  // 云管 external_project_id，= cc_bill.customer_code
  original_cost: number;            // 原价（cc_bill.original_cost）
  discount_rate: number;            // 折扣率 = (orig - final) / orig
  final_cost: number;               // 折后价（cc_bill.final_cost）
  cost: number;                     // 旧别名，= final_cost
}

interface CustomerBill {
  customer_id: number;
  customer_name: string;
  customer_code: string | null;
  month: string;
  total_original_cost: number;
  total_discount_rate: number;
  total_final_cost: number;
  total_cost: number;               // 旧别名，= total_final_cost
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
  const [syncing, setSyncing] = useState<null | 'bills' | 'usage' | 'alerts'>(null);

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

  // 手动同步云管 —— 只有 sales-manager / admin / ops 能看到。
  // bills 和 alerts 全局单次，usage-all 会遍历全部客户（耗时可能到分钟级）。
  const canManualSync = useMemo(() => {
    const r = getCurrentRoles();
    return r.includes('sales-manager') || r.includes('admin') || r.includes('root')
      || r.includes('ops') || r.includes('operation') || r.includes('operations');
  }, []);

  const runSync = async (kind: 'bills' | 'usage' | 'alerts') => {
    const m = month?.format('YYYY-MM');
    if (!m && kind !== 'usage') {
      antdMessage.warning('请先选择月份');
      return;
    }
    setSyncing(kind);
    const hide = antdMessage.loading(
      kind === 'bills' ? '正在同步账单…'
        : kind === 'usage' ? '正在同步所有客户用量（可能耗时较长）…'
        : '正在同步预警…',
      0,
    );
    try {
      let resp;
      if (kind === 'bills') {
        resp = await api.post('/api/sync/cloudcost/bills', null, { params: { month: m } });
      } else if (kind === 'alerts') {
        resp = await api.post('/api/sync/cloudcost/alerts', null, { params: { month: m } });
      } else {
        resp = await api.post('/api/sync/cloudcost/usage-all', null, { params: { days: 30 } });
      }
      const d = resp.data || {};
      const pulled = d.pulled ?? 0;
      const created = d.created ?? 0;
      const updated = d.updated ?? 0;
      const errors = d.errors ?? 0;
      antdMessage.success(
        `${kind === 'bills' ? '账单' : kind === 'usage' ? '用量' : '预警'}同步完成：`
        + `拉取 ${pulled}，新增 ${created}，更新 ${updated}`
        + (errors ? `，错误 ${errors}` : ''),
      );
      if (kind === 'bills' || kind === 'usage') {
        await loadData();
      }
    } catch (e: any) {
      antdMessage.error(
        '同步失败：' + (e?.response?.data?.detail || e?.message || '未知错误'),
      );
    } finally {
      hide();
      setSyncing(null);
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

  const totalOriginalAll = useMemo(
    () => rows.reduce((s, r) => s + Number(r.total_original_cost || r.total_cost || 0), 0),
    [rows],
  );
  const totalFinalAll = useMemo(
    () => rows.reduce((s, r) => s + Number(r.total_final_cost || r.total_cost || 0), 0),
    [rows],
  );
  const overallDiscountRate = totalOriginalAll > 0
    ? (totalOriginalAll - totalFinalAll) / totalOriginalAll : 0;
  const customerCount = rows.length;
  const resourceLinkCount = useMemo(
    () => rows.reduce((s, r) => s + r.resource_count, 0),
    [rows],
  );

  // 报表 BI 作为账单中心内的一个 Tab，只对 sales-manager / admin / root 可见。
  // 纯 sales 角色打开账单中心时只会看到 "账单聚合" 一个 Tab。
  const canSeeReports = useMemo(() => {
    const r = getCurrentRoles();
    return r.includes('sales-manager') || r.includes('admin') || r.includes('root');
  }, []);

  const customerColumns = [
    { title: '客户名称', dataIndex: 'customer_name', width: 200,
      render: (v: string, r: CustomerBill) => (
        <Space>
          <Text strong>{v}</Text>
          {r.customer_code && <Tag color="default">{r.customer_code}</Tag>}
        </Space>
      ),
    },
    { title: '关联货源数', dataIndex: 'resource_count', width: 100,
      render: (v: number) => <Tag color={v > 0 ? 'blue' : 'default'}>{v}</Tag> },
    { title: '原价合计', dataIndex: 'total_original_cost', width: 140,
      render: (v: number, r: CustomerBill) =>
        <Text type="secondary">¥{Number(v ?? r.total_cost ?? 0).toFixed(2)}</Text> },
    { title: '折扣率', dataIndex: 'total_discount_rate', width: 100,
      render: (v: number) => {
        const pct = Number(v ?? 0) * 100;
        return pct > 0
          ? <Tag color="orange">{pct.toFixed(2)}%</Tag>
          : <Text type="secondary">—</Text>;
      } },
    { title: '折后合计', dataIndex: 'total_final_cost', width: 160,
      render: (v: number, r: CustomerBill) =>
        <Text strong>¥{Number(v ?? r.total_cost ?? 0).toFixed(2)}</Text> },
    { title: '操作', width: 120, render: (_: any, r: CustomerBill) => (
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
        { title: '货源编号', dataIndex: 'resource_code', width: 160 },
        { title: '云厂商', dataIndex: 'cloud_provider', width: 90,
          render: (v: string | null) => v ? <Tag color="geekblue">{v}</Tag> : '-' },
        { title: '账号', dataIndex: 'account_name', width: 180,
          render: (v: string | null) => v || '-' },
        { title: '云账号标识', dataIndex: 'identifier_field', width: 160,
          render: (v: string | null) => v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text> },
        { title: '原价', dataIndex: 'original_cost', width: 120,
          render: (v: number, r: ResourceBill) =>
            <Text type="secondary">¥{Number(v ?? r.cost ?? 0).toFixed(2)}</Text> },
        { title: '折扣率', dataIndex: 'discount_rate', width: 90,
          render: (v: number) => {
            const pct = Number(v ?? 0) * 100;
            return pct > 0
              ? <Tag color="orange">{pct.toFixed(2)}%</Tag>
              : <Text type="secondary">—</Text>;
          } },
        { title: '折后价', dataIndex: 'final_cost', width: 130,
          render: (v: number, r: ResourceBill) =>
            <Text strong>¥{Number(v ?? r.cost ?? 0).toFixed(2)}</Text> },
      ]}
    />
  );

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
        styles={{ body: { padding: 24 } }}
      >
        <Row gutter={24}>
          <Col xs={24} md={9}>
            <Text style={{ color: '#6B7280', letterSpacing: 4 }}>BILLS · 本地聚合</Text>
            <Title level={2} style={{ color: '#1F2937', margin: '4px 0 0' }}>
              <DollarOutlined /> 账单中心
            </Title>
            <Text style={{ color: '#6B7280' }}>
              云管原始数据 × 销售分配关系（customer_resource）→ 本地聚合 · 原价 / 折扣率 / 折后价 三列贯通
            </Text>
          </Col>
          <Col xs={12} md={3}>
            <Statistic title="客户数" value={customerCount}
              valueStyle={{ color: '#1F2937', fontWeight: 600 }} />
          </Col>
          <Col xs={12} md={3}>
            <Statistic title="关联货源" value={resourceLinkCount}
              valueStyle={{ color: '#1F2937', fontWeight: 600 }} />
          </Col>
          <Col xs={12} md={3}>
            <Statistic title="原价合计" value={totalOriginalAll} precision={2} prefix="¥"
              valueStyle={{ color: '#1F2937', fontWeight: 600 }} />
          </Col>
          <Col xs={12} md={3}>
            <Statistic title="整体折扣" value={(overallDiscountRate * 100).toFixed(2)} suffix="%"
              valueStyle={{ color: '#0078D4', fontWeight: 600 }} />
          </Col>
          <Col xs={24} md={3}>
            <Statistic title="折后合计" value={totalFinalAll} precision={2} prefix="¥"
              valueStyle={{ color: '#0078D4', fontWeight: 600 }} />
          </Col>
        </Row>
      </Card>

      <Tabs
        defaultActiveKey="bills"
        items={[
          { key: 'bills', label: (<Space size={6}><DollarOutlined />账单聚合</Space>), children: (<>
      <Card
        bordered={false}
        style={{ borderRadius: 12 }}
        title={<Title level={4} style={{ margin: 0 }}>月度账单</Title>}
        extra={
          <Space wrap>
            <DatePicker picker="month" value={month} onChange={setMonth} allowClear={false} />
            <Button icon={<ReloadOutlined />} onClick={loadData}>刷新</Button>
            {canManualSync && (
              <Dropdown
                disabled={!!syncing}
                menu={{
                  items: [
                    { key: 'bills', label: '同步账单（当月 cc_bill）' },
                    { key: 'usage', label: '同步用量（全部客户，近 30 天）' },
                    { key: 'alerts', label: '同步预警规则快照（当月 cc_alert）' },
                  ],
                  onClick: ({ key }) => runSync(key as 'bills' | 'usage' | 'alerts'),
                }}
              >
                <Button
                  icon={<CloudSyncOutlined />}
                  type="primary"
                  loading={!!syncing}
                >
                  手动同步云管 <DownOutlined />
                </Button>
              </Dropdown>
            )}
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
          </>) },
          ...(canSeeReports ? [{
            key: 'reports',
            label: (<Space size={6}><BarChartOutlined />报表 BI</Space>),
            children: <Reports embedded />,
          }] : []),
        ]}
      />

      <DiscountCalculatorDrawer open={calcOpen} onClose={() => setCalcOpen(false)} />
    </div>
  );
}

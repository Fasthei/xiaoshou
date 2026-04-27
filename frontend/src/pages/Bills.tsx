import { useEffect, useMemo, useState } from 'react';
import {
  Card, Table, Tag, Typography, Space, DatePicker, Button, Statistic,
  Row, Col, Empty, Alert, Modal, Tabs, Tooltip,
  message as antdMessage,
} from 'antd';
import {
  ReloadOutlined, DollarOutlined, DownloadOutlined, CalculatorOutlined,
  CloudSyncOutlined, EditOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { api, getCurrentRoles } from '../api/axios';
import { apiBase } from '../config/casdoor';
import DiscountCalculatorDrawer from '../components/DiscountCalculatorDrawer';
import BillAdjustmentDrawer from '../components/BillAdjustmentDrawer';

const { Title, Text } = Typography;

interface ResourceBill {
  resource_id: number;
  resource_code: string | null;
  cloud_provider: string | null;
  account_name: string | null;
  identifier_field: string | null;  // 云管 external_project_id（= cc_usage.customer_code）
  original_cost: number;            // 原价 = cc_usage.total_cost (本月)
  discount_rate: number;            // 有效折扣率 0-1
  discount_rate_pct: number;        // 订单折扣率 %
  discount_override: number | null; // 账单中心覆盖的折扣率 %（若有）
  surcharge: number;                // 附加手续费
  final_cost: number;               // 折后价 = 原价 × (1 - 有效折扣率) + 手续费
  cost: number;                     // 旧别名 = final_cost
  has_allocation: boolean;          // 该 (客户, 货源) 是否有 approved 订单
  has_adjustment: boolean;          // 本月是否存在 bill_adjustment 覆盖
  adjustment_notes?: string | null;
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
  const [syncing, setSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState<string | null>(null);

  // 下钻状态: expandedRowKeys 控制客户行展开 → 子表 (按货源)
  // 再点某货源 → 弹出 drawer 级别的按日明细
  const [dayDrill, setDayDrill] = useState<{
    customer_id: number; customer_name: string; items: DayItem[]; loading: boolean;
  } | null>(null);

  // 账单覆盖 drawer（编辑某客户 × 某货源 × 当月的折扣/手续费）
  const [adjustTarget, setAdjustTarget] = useState<{
    customer_id: number; customer_name: string; resource: ResourceBill;
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
      const token = localStorage.getItem('xs_token') || '';
      const resp = await fetch(`${apiBase}/api/bills/export?month=${encodeURIComponent(m)}&format=csv`, {
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

  // 手动同步云管 —— sales / sales-manager / admin / ops 可见。
  // 销售侧也需要能拉账单（触发增量同步），权限和后端 /api/sync/cloudcost/run 一致。
  // 单按钮触发"距上次成功同步至今的增量"后端编排：bills(当月) + alerts(当月) + usage(days=时间差).
  const canManualSync = useMemo(() => {
    const r = getCurrentRoles();
    return r.includes('sales') || r.includes('sales-manager')
      || r.includes('admin') || r.includes('root')
      || r.includes('ops') || r.includes('operation') || r.includes('operations');
  }, []);

  // 加载上次同步时间（展示用）
  useEffect(() => {
    if (!canManualSync) return;
    api.get('/api/sync/cloudcost/last-sync').then(({ data }) => {
      setLastSyncAt(data?.last_sync_at ?? null);
    }).catch(() => { /* ignore */ });
  }, [canManualSync]);

  const lastSyncText = useMemo(() => {
    if (!lastSyncAt) return '尚未同步过';
    const d = dayjs(lastSyncAt);
    const diffMin = dayjs().diff(d, 'minute');
    if (diffMin < 60) return `${diffMin} 分钟前`;
    if (diffMin < 60 * 24) return `${Math.floor(diffMin / 60)} 小时前`;
    return `${Math.floor(diffMin / 60 / 24)} 天前`;
  }, [lastSyncAt]);

  const runSync = async () => {
    setSyncing(true);
    const hide = antdMessage.loading('正在同步云管数据（距上次同步的增量）…', 0);
    try {
      const { data } = await api.post('/api/sync/cloudcost/run');
      const billsR = data?.bills || {};
      const alertsR = data?.alerts || {};
      const usageR = data?.usage || {};
      const days = data?.days_covered ?? 0;
      const ok = !!data?.ok;
      antdMessage[ok ? 'success' : 'warning'](
        `同步完成（覆盖近 ${days} 天）— `
        + `账单 +${billsR.created ?? 0}/~${billsR.updated ?? 0}; `
        + `用量 +${usageR.created ?? 0}/~${usageR.updated ?? 0}; `
        + `预警 +${alertsR.created ?? 0}/~${alertsR.updated ?? 0}`
        + ((billsR.errors || alertsR.errors || usageR.errors) ? ' · 存在错误' : ''),
      );
      setLastSyncAt(data?.started_at ?? null);
      await loadData();
    } catch (e: any) {
      antdMessage.error(
        '同步失败：' + (e?.response?.data?.detail || e?.message || '未知错误'),
      );
    } finally {
      hide();
      setSyncing(false);
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
        { title: '货源编号', dataIndex: 'resource_code', width: 140 },
        { title: '云厂商', dataIndex: 'cloud_provider', width: 80,
          render: (v: string | null) => v ? <Tag color="geekblue">{v}</Tag> : '-' },
        { title: '账号', dataIndex: 'account_name', width: 150,
          render: (v: string | null) => v || '-' },
        { title: '云账号标识', dataIndex: 'identifier_field', width: 150,
          render: (v: string | null) => v ? <Tag>{v}</Tag> : <Text type="secondary">—</Text> },
        { title: '原价 (用量)', dataIndex: 'original_cost', width: 110,
          render: (v: number, r: ResourceBill) =>
            <Text type="secondary">¥{Number(v ?? r.cost ?? 0).toFixed(2)}</Text> },
        {
          title: '折扣率',
          width: 130,
          render: (_: unknown, r: ResourceBill) => {
            const pct = Number(r.discount_rate ?? 0) * 100;
            const orderPct = Number(r.discount_rate_pct ?? 0);
            const chip = pct > 0
              ? <Tag color="orange">{pct.toFixed(2)}%</Tag>
              : <Text type="secondary">—</Text>;
            if (r.has_adjustment && r.discount_override != null) {
              return (
                <Tooltip title={`订单折扣 ${orderPct.toFixed(2)}% → 账单中心已覆盖为 ${(r.discount_override).toFixed(2)}%`}>
                  <Space size={4}>{chip}<Tag color="purple">覆盖</Tag></Space>
                </Tooltip>
              );
            }
            if (!r.has_allocation && pct === 0) {
              return <Tooltip title="该货源无 approved 订单 → 默认 0%"><Text type="secondary">—</Text></Tooltip>;
            }
            return chip;
          },
        },
        { title: '手续费', dataIndex: 'surcharge', width: 100,
          render: (v: number) => (
            v ? <Text style={{ color: v > 0 ? '#f59e0b' : '#16a34a' }}>¥{Number(v).toFixed(2)}</Text>
              : <Text type="secondary">—</Text>
          ),
        },
        { title: '折后价', dataIndex: 'final_cost', width: 120,
          render: (v: number, r: ResourceBill) =>
            <Text strong>¥{Number(v ?? r.cost ?? 0).toFixed(2)}</Text> },
        {
          title: '操作',
          width: 100,
          render: (_: unknown, r: ResourceBill) => (
            <Button
              size="small"
              type="link"
              icon={<EditOutlined />}
              onClick={() => setAdjustTarget({
                customer_id: row.customer_id,
                customer_name: row.customer_name,
                resource: r,
              })}
            >
              编辑
            </Button>
          ),
        },
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
              <Tooltip
                title={`上次同步：${lastSyncText}。点击会拉取距上次至今（bills/alerts 当月覆盖 + usage 按天数）的云管数据写入销售系统。`}
              >
                <Button
                  icon={<CloudSyncOutlined />}
                  type="primary"
                  loading={syncing}
                  onClick={runSync}
                >
                  同步云管
                </Button>
              </Tooltip>
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
        ]}
      />

      <DiscountCalculatorDrawer open={calcOpen} onClose={() => setCalcOpen(false)} />

      {/* 账单覆盖 (客户 × 货源 × 月) drawer */}
      {adjustTarget && (
        <BillAdjustmentDrawer
          open
          onClose={() => setAdjustTarget(null)}
          onSaved={() => loadData()}
          customer_id={adjustTarget.customer_id}
          customer_name={adjustTarget.customer_name}
          resource_id={adjustTarget.resource.resource_id}
          resource_code={adjustTarget.resource.resource_code}
          identifier_field={adjustTarget.resource.identifier_field}
          month={month?.format('YYYY-MM') || ''}
          original_cost={Number(adjustTarget.resource.original_cost || 0)}
          discount_rate_pct={Number(adjustTarget.resource.discount_rate_pct || 0)}
          discount_override={adjustTarget.resource.discount_override}
          surcharge={Number(adjustTarget.resource.surcharge || 0)}
          notes={adjustTarget.resource.adjustment_notes}
          has_adjustment={adjustTarget.resource.has_adjustment}
        />
      )}
    </div>
  );
}

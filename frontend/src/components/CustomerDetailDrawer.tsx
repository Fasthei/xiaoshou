import { useEffect, useMemo, useState } from 'react';
import {
  Drawer, Tabs, Descriptions, Tag, Space, Typography, List, Avatar, Empty,
  Skeleton, Button, Card, Timeline, Select, Input, Modal, Form, Table, Alert,
  Statistic, Row, Col, DatePicker,
  Upload, InputNumber, Popconfirm,
  message as antdMessage,
} from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  CloudServerOutlined, SyncOutlined, LinkOutlined, BulbOutlined,
  UserSwitchOutlined, HistoryOutlined, FileTextOutlined, BarChartOutlined,
  WarningOutlined, ProfileOutlined, CustomerServiceOutlined,
  FullscreenOutlined, FullscreenExitOutlined,
  ZoomInOutlined, ZoomOutOutlined, CloseOutlined,
  UploadOutlined, DownloadOutlined,
  DeleteOutlined, PlusOutlined, PaperClipOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { api } from '../api/axios';
import type { Customer } from '../types';
import HealthRadar from './HealthRadar';
import CustomerInsightPanel from './CustomerInsightPanel';
import CustomerProfileTab from './CustomerProfileTab';

const { Text } = Typography;

interface CloudCostResource {
  resource_id: number;
  resource_name: string;
  provider: string;
  supply_source_id?: number | null;
  supplier_name?: string | null;
  external_project_id?: string | null;
  status?: string | null;
}

const PROVIDER_COLOR: Record<string, string> = {
  aws: 'orange', azure: 'blue', gcp: 'red', aliyun: 'cyan',
};

export default function CustomerDetailDrawer({
  open, customer, onClose,
}: {
  open: boolean;
  customer: Customer | null;
  onClose: () => void;
}) {
  // 抽屉尺寸 / 全屏 控制
  const DEFAULT_W = 640;
  const MIN_W = 480;
  const STEP = 200;
  const [drawerWidth, setDrawerWidth] = useState<number | string>(DEFAULT_W);
  const [fullscreen, setFullscreen] = useState(false);

  const resetSize = () => { setDrawerWidth(DEFAULT_W); setFullscreen(false); };
  const zoomOut = () => {
    if (fullscreen) { setFullscreen(false); setDrawerWidth(DEFAULT_W); return; }
    setDrawerWidth((w) =>
      typeof w === 'number' ? Math.max(MIN_W, w - STEP) : DEFAULT_W
    );
  };
  const zoomIn = () => {
    if (fullscreen) return;
    setDrawerWidth((w) => {
      const maxPx = window.innerWidth;
      const next = typeof w === 'number' ? Math.min(maxPx, w + STEP) : DEFAULT_W + STEP;
      if (next >= maxPx) { setFullscreen(true); return '100vw'; }
      return next;
    });
  };
  const toggleFullscreen = () => {
    if (fullscreen) { setFullscreen(false); setDrawerWidth(DEFAULT_W); }
    else { setFullscreen(true); setDrawerWidth('100vw'); }
  };

  // 每次重新打开时回到默认尺寸
  useEffect(() => { if (open) resetSize(); /* eslint-disable-next-line */ }, [open]);

  const [loading, setLoading] = useState(false);
  const [resources, setResources] = useState<CloudCostResource[]>([]);
  const [matchField, setMatchField] = useState('');
  const [health, setHealth] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [salesUsers, setSalesUsers] = useState<any[]>([]);
  const [assignLog, setAssignLog] = useState<any[]>([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignForm] = Form.useForm<{ sales_user_id?: number | null; reason?: string }>();

  // --- Milestone 2: 4 new tabs state ---
  const [contracts, setContracts] = useState<any[]>([]);
  const [contractsLoading, setContractsLoading] = useState(false);
  // Contract create modal + file upload state
  const [contractModalOpen, setContractModalOpen] = useState(false);
  const [contractForm] = Form.useForm();
  const [contractSaving, setContractSaving] = useState(false);
  const [uploadingId, setUploadingId] = useState<number | null>(null);
  const [usageSummary, setUsageSummary] = useState<any>(null);
  const [usageErr, setUsageErr] = useState(false);
  const [usageLoading, setUsageLoading] = useState(false);
  const [usageSyncing, setUsageSyncing] = useState(false);
  const [usageLastSync, setUsageLastSync] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [bills, setBills] = useState<any[]>([]);
  const [bridgeErr, setBridgeErr] = useState<string | null>(null);
  const [bridgeLoading, setBridgeLoading] = useState(false);
  const [alertsSyncing, setAlertsSyncing] = useState(false);
  const [billsSyncing, setBillsSyncing] = useState(false);
  const [alertsLastSync, setAlertsLastSync] = useState<string | null>(null);
  const [billsLastSync, setBillsLastSync] = useState<string | null>(null);
  const [historyBills, setHistoryBills] = useState<any[]>([]);
  const [historyErr, setHistoryErr] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySyncing, setHistorySyncing] = useState(false);
  const [historyLastSync, setHistoryLastSync] = useState<string | null>(null);
  const [historyMonth, setHistoryMonth] = useState<Dayjs | null>(dayjs());
  const [historyDate, setHistoryDate] = useState<Dayjs | null>(null);
  const [historyStatus, setHistoryStatus] = useState<string | undefined>(undefined);

  // --- Ticket mirror tab state ---
  interface LocalTicket {
    id: number;
    ticket_code: string;
    title: string | null;
    status: string | null;
    created_at: string | null;
    updated_at: string | null;
  }
  const [tickets, setTickets] = useState<LocalTicket[]>([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);
  const [ticketsSyncing, setTicketsSyncing] = useState(false);

  // 工单聚合统计 (顶部 Statistic 卡)
  interface TicketStats {
    total: number;
    by_status: Record<string, number>;
    last_30d_count: number;
  }
  const [ticketStats, setTicketStats] = useState<TicketStats | null>(null);

  const loadTicketStats = async () => {
    if (!customer) return;
    try {
      const { data } = await api.get<TicketStats>(
        `/api/customers/${customer.id}/tickets/stats`,
      );
      if (data && typeof data === 'object') {
        setTicketStats({
          total: Number(data.total || 0),
          by_status: data.by_status && typeof data.by_status === 'object' ? data.by_status : {},
          last_30d_count: Number(data.last_30d_count || 0),
        });
      } else {
        setTicketStats(null);
      }
    } catch {
      setTicketStats(null);
    }
  };

  const loadTickets = async () => {
    if (!customer) return;
    setTicketsLoading(true);
    try {
      const { data } = await api.get<LocalTicket[]>(`/api/customers/${customer.id}/tickets`);
      setTickets(Array.isArray(data) ? data : []);
    } catch {
      setTickets([]);
    } finally {
      setTicketsLoading(false);
    }
    // 并发拉统计,不阻塞表格渲染
    loadTicketStats();
  };

  const syncTickets = async () => {
    setTicketsSyncing(true);
    try {
      const { data } = await api.post('/api/sync/tickets/from-gongdan');
      antdMessage.success(
        `同步完成：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`
      );
      loadTickets();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '同步失败');
    } finally {
      setTicketsSyncing(false);
    }
  };

  const currentMonth = () => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
  };

  const loadContracts = async () => {
    if (!customer) return;
    setContractsLoading(true);
    try {
      const { data } = await api.get(`/api/customers/${customer.id}/contracts`);
      setContracts(Array.isArray(data) ? data : []);
    } catch {
      setContracts([]);
    } finally {
      setContractsLoading(false);
    }
  };

  const openContractModal = () => {
    contractForm.resetFields();
    setContractModalOpen(true);
  };

  const submitContract = async () => {
    if (!customer) return;
    const v = await contractForm.validateFields();
    setContractSaving(true);
    try {
      const payload: any = {
        customer_id: customer.id,
        contract_code: v.contract_code,
        title: v.title || null,
        amount: v.amount ?? null,
        status: v.status || 'active',
        notes: v.notes || null,
        start_date: v.start_date ? dayjs(v.start_date).format('YYYY-MM-DD') : null,
        end_date: v.end_date ? dayjs(v.end_date).format('YYYY-MM-DD') : null,
      };
      await api.post('/api/contracts', payload);
      antdMessage.success('合同已创建，可在列表中上传附件');
      setContractModalOpen(false);
      loadContracts();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '创建合同失败');
    } finally {
      setContractSaving(false);
    }
  };

  const uploadContractFile = async (contractId: number, file: File): Promise<boolean> => {
    // antd Upload size/type hints — server is source of truth
    const MAX = 10 * 1024 * 1024;
    const OK_EXT = ['pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png'];
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!OK_EXT.includes(ext)) {
      antdMessage.error('仅支持 PDF/Word/JPG/PNG');
      return false;
    }
    if (file.size > MAX) {
      antdMessage.error('文件大小不能超过 10MB');
      return false;
    }
    setUploadingId(contractId);
    try {
      const fd = new FormData();
      fd.append('file', file);
      await api.post(`/api/contracts/${contractId}/upload`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      antdMessage.success('上传成功');
      loadContracts();
      return true;
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '上传失败');
      return false;
    } finally {
      setUploadingId(null);
    }
  };

  const downloadContractFile = async (contractId: number) => {
    try {
      const { data } = await api.get(`/api/contracts/${contractId}/download`);
      if (data?.url) {
        window.open(data.url, '_blank', 'noopener');
      } else {
        antdMessage.error('下载链接不可用');
      }
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '获取下载链接失败');
    }
  };

  const removeContractFile = async (contractId: number) => {
    try {
      await api.delete(`/api/contracts/${contractId}/file`);
      antdMessage.success('文件已删除');
      loadContracts();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '删除文件失败');
    }
  };

  const humanSize = (n?: number | null) => {
    if (!n) return '';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 / 1024).toFixed(2)} MB`;
  };

  const loadUsage = async () => {
    if (!customer) return;
    setUsageLoading(true);
    setUsageErr(false);
    try {
      const { data } = await api.get(`/api/customers/${customer.id}/local-usage`, {
        params: { days: 30 },
      });
      setUsageSummary(data);
      setUsageLastSync(data?.last_sync_at || null);
    } catch {
      setUsageSummary(null);
      setUsageErr(true);
    } finally {
      setUsageLoading(false);
    }
  };

  const syncUsage = async () => {
    if (!customer) return;
    setUsageSyncing(true);
    try {
      const { data } = await api.post('/api/sync/cloudcost/usage', null, {
        params: { customer_id: customer.id, days: 30 },
      });
      if (data?.warning) {
        antdMessage.warning(
          `同步完成 (命中 ${data.matched_accounts} 货源, 新增 ${data.created}, 更新 ${data.updated}): ${data.warning}`
        );
      } else {
        antdMessage.success(
          `同步完成：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`
        );
      }
      loadUsage();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '同步用量失败');
    } finally {
      setUsageSyncing(false);
    }
  };

  const loadBridge = async () => {
    if (!customer) return;
    setBridgeLoading(true);
    setBridgeErr(null);
    const month = currentMonth();
    try {
      const [aResp, bResp] = await Promise.allSettled([
        api.get(`/api/customers/${customer.id}/local-alerts`, { params: { month } }),
        api.get(`/api/customers/${customer.id}/local-bills`, { params: { month } }),
      ]);
      if (aResp.status === 'fulfilled') {
        const payload = aResp.value.data;
        setAlerts(Array.isArray(payload?.items) ? payload.items : []);
        setAlertsLastSync(payload?.last_sync_at || null);
      } else {
        setAlerts([]);
        setBridgeErr('本地预警读取失败');
      }
      if (bResp.status === 'fulfilled') {
        const payload = bResp.value.data;
        setBills(Array.isArray(payload?.items) ? payload.items : []);
        setBillsLastSync(payload?.last_sync_at || null);
      } else {
        setBills([]);
        if (!bridgeErr) setBridgeErr('本地账单读取失败');
      }
    } finally {
      setBridgeLoading(false);
    }
  };

  const syncAlerts = async () => {
    if (!customer) return;
    setAlertsSyncing(true);
    try {
      const { data } = await api.post('/api/sync/cloudcost/alerts', null, {
        params: { month: currentMonth() },
      });
      antdMessage.success(
        `同步完成：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`
      );
      loadBridge();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '同步预警失败');
    } finally {
      setAlertsSyncing(false);
    }
  };

  const syncBills = async (month?: string) => {
    if (!customer) return;
    setBillsSyncing(true);
    try {
      const { data } = await api.post('/api/sync/cloudcost/bills', null, {
        params: { month: month || currentMonth() },
      });
      antdMessage.success(
        `同步完成：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`
      );
      loadBridge();
      loadHistoryBills();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '同步账单失败');
    } finally {
      setBillsSyncing(false);
    }
  };

  const loadHistoryBills = async (monthOverride?: Dayjs | null) => {
    if (!customer) return;
    setHistoryLoading(true);
    setHistoryErr(null);
    const monthArg = monthOverride === undefined ? historyMonth : monthOverride;
    const params: Record<string, any> = {};
    if (monthArg) params.month = monthArg.format('YYYY-MM');
    try {
      const { data } = await api.get(`/api/customers/${customer.id}/local-bills`, { params });
      setHistoryBills(Array.isArray(data?.items) ? data.items : []);
      setHistoryLastSync(data?.last_sync_at || null);
    } catch {
      setHistoryBills([]);
      setHistoryErr('本地账单读取失败');
    } finally {
      setHistoryLoading(false);
    }
  };

  const syncHistoryBills = async () => {
    const month = historyMonth ? historyMonth.format('YYYY-MM') : currentMonth();
    setHistorySyncing(true);
    try {
      const { data } = await api.post('/api/sync/cloudcost/bills', null, {
        params: { month },
      });
      antdMessage.success(
        `同步完成 (${month})：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`
      );
      loadHistoryBills();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '同步账单失败');
    } finally {
      setHistorySyncing(false);
    }
  };

  const loadResources = async () => {
    if (!customer) return;
    setLoading(true);
    try {
      const { data } = await api.get(`/api/customers/${customer.id}/resources`);
      setResources(data.items || []);
      setMatchField(data.match_field || '');
    } catch (e) {
      setResources([]);
    } finally {
      setLoading(false);
    }
  };

  const loadAssign = async () => {
    if (!customer) return;
    const [s, l] = await Promise.all([
      api.get('/api/sales/users').then((r) => r.data).catch(() => []),
      api.get(`/api/customers/${customer.id}/assignment-log`).then((r) => r.data).catch(() => []),
    ]);
    setSalesUsers(s);
    setAssignLog(l);
  };

  useEffect(() => {
    if (open && customer) {
      loadResources();
      api.get(`/api/customers/${customer.id}/health`).then(({ data }) => setHealth(data)).catch(() => setHealth(null));
      api.get(`/api/customers/${customer.id}/timeline`).then(({ data }) => setTimeline(data)).catch(() => setTimeline([]));
      loadAssign();
      loadContracts();
      loadUsage();
      loadBridge();
      loadHistoryBills();
      loadTickets();
    }
    // eslint-disable-next-line
  }, [open, customer?.id]);

  const openAssignModal = () => {
    assignForm.resetFields();
    assignForm.setFieldsValue({ sales_user_id: customer?.sales_user_id ?? null });
    setAssignOpen(true);
  };

  const submitAssign = async () => {
    if (!customer) return;
    const v = await assignForm.validateFields();
    await api.patch(`/api/customers/${customer.id}/assign`, v);
    antdMessage.success('分配已更新');
    setAssignOpen(false);
    loadAssign();
  };

  const salesUserById = (id?: number | null) => salesUsers.find((u) => u.id === id);
  const currentSalesUser = salesUserById(customer?.sales_user_id);

  const filteredHistoryBills = useMemo(() => {
    const dayFilter = historyDate ? historyDate.format('YYYY-MM-DD') : null;
    return historyBills.filter((b: any) => {
      if (historyStatus && b.status !== historyStatus) return false;
      if (dayFilter) {
        const candidates = [
          b.bill_date, b.date, b.period, b.created_at, b.billed_at, b.billing_date,
        ].filter(Boolean).map((v: any) => String(v).slice(0, 10));
        if (!candidates.includes(dayFilter)) return false;
      }
      return true;
    });
  }, [historyBills, historyDate, historyStatus]);

  const tierBadge = (tier?: string) => {
    const map: Record<string, string> = { KEY: '#ec4899', EXCLUSIVE: '#f59e0b', NORMAL: '#4f46e5' };
    return tier ? <Tag color={map[tier] || 'default'}>{tier}</Tag> : null;
  };

  return (
    <Drawer
      title={
        customer ? (
          <Space>
            <Avatar size={40} style={{ background: 'linear-gradient(135deg, #4f46e5, #ec4899)' }}>
              {customer.customer_name?.[0]}
            </Avatar>
            <div>
              <Text strong style={{ fontSize: 16 }}>{customer.customer_name}</Text>
              <div><Text type="secondary" style={{ fontSize: 12 }}>{customer.customer_code}</Text></div>
            </div>
          </Space>
        ) : '客户详情'
      }
      extra={
        <Space size={4}>
          <Button
            size="small" type="text" icon={<ZoomOutOutlined />}
            onClick={zoomOut} title="缩小" disabled={!fullscreen && typeof drawerWidth === 'number' && drawerWidth <= MIN_W}
          />
          <Button
            size="small" type="text" icon={<ZoomInOutlined />}
            onClick={zoomIn} title="放大" disabled={fullscreen}
          />
          <Button
            size="small" type="text"
            icon={fullscreen ? <FullscreenExitOutlined /> : <FullscreenOutlined />}
            onClick={toggleFullscreen} title={fullscreen ? '退出全屏' : '全屏'}
          />
          <Button
            size="small" type="text" icon={<CloseOutlined />}
            onClick={onClose} title="关闭"
          />
        </Space>
      }
      open={open} onClose={onClose} width={drawerWidth} destroyOnClose
      closable={false}
      maskClosable={!fullscreen}
    >
      {customer && (
        <Tabs
          items={[
            {
              key: 'info',
              label: '基本信息',
              children: (
                <Descriptions column={1} bordered size="small">
                  <Descriptions.Item label="客户编号">{customer.customer_code}</Descriptions.Item>
                  <Descriptions.Item label="客户名称">{customer.customer_name}</Descriptions.Item>
                  <Descriptions.Item label="简称">{customer.customer_short_name || '-'}</Descriptions.Item>
                  <Descriptions.Item label="行业">{customer.industry || '-'}</Descriptions.Item>
                  <Descriptions.Item label="地区">{customer.region || '-'}</Descriptions.Item>
                  <Descriptions.Item label="状态">
                    {(() => {
                      const s = customer.customer_status;
                      const colorMap: Record<string, string> = {
                        active: 'green', potential: 'purple', prospect: 'purple',
                        inactive: 'default', frozen: 'red',
                      };
                      const labelMap: Record<string, string> = {
                        active: '客户池', potential: '潜在', prospect: '潜在',
                        inactive: '停用', frozen: '冻结',
                      };
                      return <Tag color={colorMap[s] || 'default'}>{labelMap[s] || s}</Tag>;
                    })()}
                  </Descriptions.Item>
                  {customer.source_label ? (
                    <Descriptions.Item label="来源">
                      <Tag color="magenta">{customer.source_label}</Tag>
                    </Descriptions.Item>
                  ) : null}
                  <Descriptions.Item label="当月消耗">{customer.current_month_consumption ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">{customer.created_at || '-'}</Descriptions.Item>
                </Descriptions>
              ),
            },
            {
              key: 'timeline',
              label: (<Space>时间线 <Tag color="cyan">{timeline.length}</Tag></Space>),
              children: timeline.length === 0 ? (
                <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无事件" />
              ) : (
                <Timeline
                  items={timeline.map((e) => ({
                    color: e.color || 'blue',
                    children: (
                      <Space direction="vertical" size={2}>
                        <Text strong>{e.title}</Text>
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {new Date(e.at).toLocaleString()} · {e.kind}
                        </Text>
                        {e.detail ? <Text>{e.detail}</Text> : null}
                      </Space>
                    ),
                  }))}
                />
              ),
            },
            {
              key: 'health',
              label: '健康分',
              children: health ? (
                <Space direction="vertical" size="large" style={{ width: '100%' }}>
                  <Space style={{ width: '100%', justifyContent: 'center' }}>
                    <div style={{ textAlign: 'center' }}>
                      <div style={{
                        fontSize: 56, fontWeight: 700,
                        color: health.tier === 'green' ? '#16a34a' : health.tier === 'yellow' ? '#f59e0b' : '#ef4444',
                      }}>{health.score}</div>
                      <Tag color={health.tier === 'green' ? 'green' : health.tier === 'yellow' ? 'orange' : 'red'}>
                        {health.tier === 'green' ? '健康' : health.tier === 'yellow' ? '关注' : '预警'}
                      </Tag>
                    </div>
                  </Space>
                  <div style={{ display: 'flex', justifyContent: 'center' }}>
                    <HealthRadar
                      values={[health.radar.consumption, health.radar.activity, health.radar.engagement, health.radar.completeness]}
                      labels={['消耗', '活跃', '粘性', '完整度']}
                    />
                  </div>
                  {health.tips?.filter(Boolean).length ? (
                    <Card size="small" title="建议">
                      {health.tips.filter(Boolean).map((t: string, i: number) => (
                        <div key={i}>• {t}</div>
                      ))}
                    </Card>
                  ) : null}
                </Space>
              ) : <Skeleton active />,
            },
            {
              key: 'assign',
              label: (
                <Space><UserSwitchOutlined />分配 {currentSalesUser ? <Tag color="geekblue">{currentSalesUser.name}</Tag> : <Tag>未分配</Tag>}</Space>
              ),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Card size="small">
                    <Descriptions column={1} size="small">
                      <Descriptions.Item label="当前销售">
                        {currentSalesUser ? (
                          <Space>
                            <Avatar size="small" style={{ background: '#6366f1' }}>{currentSalesUser.name[0]}</Avatar>
                            <Text strong>{currentSalesUser.name}</Text>
                            {currentSalesUser.email ? <Text type="secondary">· {currentSalesUser.email}</Text> : null}
                          </Space>
                        ) : <Tag>未分配</Tag>}
                      </Descriptions.Item>
                      <Descriptions.Item label="来源系统">{customer.source_system || '—'}</Descriptions.Item>
                      <Descriptions.Item label="来源 ID / URL">
                        {customer.source_id ? (
                          customer.source_id.startsWith('http') ? (
                            <a href={customer.source_id} target="_blank" rel="noreferrer">{customer.source_id}</a>
                          ) : customer.source_id
                        ) : '—'}
                      </Descriptions.Item>
                    </Descriptions>
                    <div style={{ marginTop: 12 }}>
                      <Button type="primary" icon={<UserSwitchOutlined />} onClick={openAssignModal}>
                        {currentSalesUser ? '再分配 / 修改' : '分配销售'}
                      </Button>
                    </div>
                  </Card>

                  <Card size="small" title={<Space><HistoryOutlined />分配历史 <Tag>{assignLog.length}</Tag></Space>}>
                    {assignLog.length === 0 ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无分配记录" />
                    ) : (
                      <Timeline
                        items={assignLog.map((l: any) => {
                          const from = salesUserById(l.from_user_id)?.name || (l.from_user_id ? `#${l.from_user_id}` : '—');
                          const to = salesUserById(l.to_user_id)?.name || (l.to_user_id ? `#${l.to_user_id}` : '取消分配');
                          const triggerColor = l.trigger === 'auto' ? 'green' : 'blue';
                          return {
                            color: triggerColor,
                            children: (
                              <Space direction="vertical" size={2}>
                                <Space>
                                  <Text>{from}</Text><Text type="secondary">→</Text><Text strong>{to}</Text>
                                  <Tag color={triggerColor}>{l.trigger}</Tag>
                                  {l.rule_id ? <Tag color="gold">规则#{l.rule_id}</Tag> : null}
                                </Space>
                                <Text type="secondary" style={{ fontSize: 12 }}>{new Date(l.at).toLocaleString()}</Text>
                                {l.reason ? <Text>{l.reason}</Text> : null}
                              </Space>
                            ),
                          };
                        })}
                      />
                    )}
                  </Card>
                </Space>
              ),
            },
            {
              key: 'profile',
              label: <Space>📋 档案 / 跟进</Space>,
              children: <CustomerProfileTab customerId={customer.id} />,
            },
            {
              key: 'insight',
              label: (
                <Space><BulbOutlined style={{ color: '#f59e0b' }} />AI 洞察</Space>
              ),
              children: <CustomerInsightPanel customerId={customer.id} />,
            },
            {
              key: 'contracts',
              label: (<Space><FileTextOutlined />合同 <Tag color="purple">{contracts.length}</Tag></Space>),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Text type="secondary">
                      支持上传 PDF / Word / 图片 (≤10MB), 存储于 Azure Blob
                    </Text>
                    <Space>
                      <Button size="small" icon={<SyncOutlined />} onClick={loadContracts} loading={contractsLoading}>
                        刷新
                      </Button>
                      <Button size="small" type="primary" icon={<PlusOutlined />} onClick={openContractModal}>
                        新建合同
                      </Button>
                    </Space>
                  </Space>
                  <Table
                    size="small"
                    rowKey="id"
                    loading={contractsLoading}
                    dataSource={contracts}
                    locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无合同" /> }}
                    pagination={false}
                    scroll={{ x: 720 }}
                    columns={[
                      { title: '合同号', dataIndex: 'contract_code', width: 140, fixed: 'left' as const,
                        render: (v: string) => <code style={{ color: '#4f46e5' }}>{v}</code> },
                      { title: '标题', dataIndex: 'title', ellipsis: true },
                      { title: '金额', dataIndex: 'amount', width: 100,
                        render: (v: any) => v ? `¥ ${v}` : '—' },
                      { title: '起止', width: 180,
                        render: (_: any, r: any) =>
                          `${r.start_date || '—'} ~ ${r.end_date || '—'}` },
                      { title: '状态', dataIndex: 'status', width: 80,
                        render: (s: string) => <Tag color={s === 'active' ? 'green' : 'default'}>{s || 'active'}</Tag> },
                      {
                        title: '文件', width: 180,
                        render: (_: any, r: any) => r.file_url ? (
                          <Space size={4}>
                            <PaperClipOutlined style={{ color: '#4f46e5' }} />
                            <Text style={{ fontSize: 12, maxWidth: 100 }} ellipsis={{ tooltip: r.file_name }}>
                              {r.file_name || '附件'}
                            </Text>
                            <Text type="secondary" style={{ fontSize: 11 }}>{humanSize(r.file_size)}</Text>
                          </Space>
                        ) : <Text type="secondary" style={{ fontSize: 12 }}>未上传</Text>,
                      },
                      {
                        title: '操作', width: 200, fixed: 'right' as const,
                        render: (_: any, r: any) => (
                          <Space size={4}>
                            <Upload
                              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                              maxCount={1}
                              showUploadList={false}
                              beforeUpload={(file: UploadFile & File) => {
                                uploadContractFile(r.id, file as unknown as File);
                                return false; // prevent default auto-upload
                              }}
                            >
                              <Button size="small" type="link" icon={<UploadOutlined />}
                                loading={uploadingId === r.id}>
                                {r.file_url ? '替换' : '上传'}
                              </Button>
                            </Upload>
                            {r.file_url ? (
                              <>
                                <Button size="small" type="link" icon={<DownloadOutlined />}
                                  onClick={() => downloadContractFile(r.id)}>下载</Button>
                                <Popconfirm title="确定删除该合同文件?" onConfirm={() => removeContractFile(r.id)}
                                  okText="删除" cancelText="取消" okButtonProps={{ danger: true }}>
                                  <Button size="small" type="link" danger icon={<DeleteOutlined />} />
                                </Popconfirm>
                              </>
                            ) : null}
                          </Space>
                        ),
                      },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'usage',
              label: (<Space><BarChartOutlined />用量</Space>),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      来源：本地 cc_usage 表
                      {usageLastSync ? (
                        <Tag style={{ marginLeft: 6 }} color="geekblue">
                          上次同步 {new Date(usageLastSync).toLocaleString()}
                        </Tag>
                      ) : <Tag style={{ marginLeft: 6 }}>未同步</Tag>}
                    </Text>
                    <Space>
                      <Button
                        size="small"
                        type="primary"
                        icon={<SyncOutlined spin={usageSyncing} />}
                        loading={usageSyncing}
                        onClick={syncUsage}
                      >
                        🔄 同步本月
                      </Button>
                      <Button size="small" icon={<SyncOutlined />} onClick={loadUsage} loading={usageLoading}>
                        刷新
                      </Button>
                    </Space>
                  </Space>
                  {usageLoading ? <Skeleton active /> : (usageErr || !usageSummary) ? (
                    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无用量数据（请点击 “🔄 同步本月”）" />
                  ) : (() => {
                const totalUsage = Number(usageSummary.total_usage ?? 0);
                const totalCost = Number(usageSummary.total_cost ?? 0);
                const recordCount = Number(usageSummary.record_count ?? 0);
                const startDate = usageSummary.start_date || '—';
                const endDate = usageSummary.end_date || '—';
                const byService = Array.isArray(usageSummary.by_service) ? usageSummary.by_service : [];
                const byDate = Array.isArray(usageSummary.by_date) ? usageSummary.by_date : [];
                const isEmpty = totalUsage === 0 && totalCost === 0 && recordCount === 0;
                return (
                  <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                    <Card size="small">
                      <Row gutter={16}>
                        <Col span={8}>
                          <Statistic
                            title="总用量"
                            value={totalUsage}
                            precision={totalUsage % 1 === 0 ? 0 : 2}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title="总成本"
                            value={totalCost}
                            prefix="¥"
                            precision={2}
                            valueStyle={{ color: totalCost > 0 ? '#ec4899' : undefined }}
                          />
                        </Col>
                        <Col span={8}>
                          <Statistic
                            title="记录数"
                            value={recordCount}
                            valueStyle={{ color: recordCount > 0 ? '#4f46e5' : undefined }}
                          />
                        </Col>
                      </Row>
                    </Card>
                    <Card size="small" title="统计区间">
                      <Descriptions column={2} size="small">
                        <Descriptions.Item label="起始日期">{startDate}</Descriptions.Item>
                        <Descriptions.Item label="截止日期">{endDate}</Descriptions.Item>
                        {usageSummary.customer_id !== undefined ? (
                          <Descriptions.Item label="客户 ID">{usageSummary.customer_id}</Descriptions.Item>
                        ) : null}
                      </Descriptions>
                    </Card>
                    {isEmpty ? (
                      <Alert
                        type="info"
                        showIcon
                        message="区间内暂无用量记录"
                        description="该客户在当前统计区间尚未产生用量或成本数据。"
                      />
                    ) : null}
                    {byService.length > 0 ? (
                      <Card size="small" title="按服务">
                        <Table
                          size="small"
                          rowKey={(r: any, i) => r.service || r.name || String(i)}
                          pagination={false}
                          dataSource={byService}
                          columns={[
                            { title: '服务', dataIndex: 'service', render: (v, r: any) => v || r.name || '—' },
                            { title: '用量', dataIndex: 'usage', align: 'right',
                              render: (v: any) => v ?? '—' },
                            { title: '成本', dataIndex: 'cost', align: 'right',
                              render: (v: any) => v !== undefined && v !== null ? `¥ ${Number(v).toFixed(2)}` : '—' },
                          ]}
                        />
                      </Card>
                    ) : null}
                    {byDate.length > 0 ? (
                      <Card size="small" title="按日期">
                        <Table
                          size="small"
                          rowKey={(r: any, i) => r.date || String(i)}
                          pagination={{ pageSize: 10, size: 'small' }}
                          dataSource={byDate}
                          columns={[
                            { title: '日期', dataIndex: 'date' },
                            { title: '用量', dataIndex: 'usage', align: 'right',
                              render: (v: any) => v ?? '—' },
                            { title: '成本', dataIndex: 'cost', align: 'right',
                              render: (v: any) => v !== undefined && v !== null ? `¥ ${Number(v).toFixed(2)}` : '—' },
                          ]}
                        />
                      </Card>
                    ) : null}
                  </Space>
                );
              })()}
                </Space>
              ),
            },
            {
              key: 'alerts-bills',
              label: (<Space><WarningOutlined />预警 &amp; 收款 <Tag color="gold">{alerts.length + bills.length}</Tag></Space>),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {bridgeErr ? (
                    <Alert message={bridgeErr} type="warning" showIcon closable={false} />
                  ) : null}
                  <Card
                    size="small"
                    title={
                      <Space>
                        预警 <Tag>{alerts.length}</Tag>
                        {alertsLastSync ? (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            · 上次同步 {new Date(alertsLastSync).toLocaleString()}
                          </Text>
                        ) : null}
                      </Space>
                    }
                    extra={
                      <Space>
                        <Button
                          size="small" type="primary"
                          icon={<SyncOutlined spin={alertsSyncing} />}
                          loading={alertsSyncing}
                          onClick={syncAlerts}
                        >
                          🔄 同步本月
                        </Button>
                        <Button size="small" icon={<SyncOutlined />} loading={bridgeLoading} onClick={loadBridge}>
                          刷新
                        </Button>
                      </Space>
                    }
                  >
                    {alerts.length === 0 ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本月暂无预警（请点击“🔄 同步本月”）" />
                    ) : (
                      <List
                        size="small"
                        dataSource={alerts}
                        renderItem={(a: any) => (
                          <List.Item>
                            <Space direction="vertical" size={2}>
                              <Space>
                                <Text strong>{a.rule_name || a.title || '预警'}</Text>
                                {a.triggered ? <Tag color="red">已触发</Tag> : <Tag color="default">未触发</Tag>}
                                {a.threshold_type ? <Tag color="orange">{a.threshold_type}</Tag> : null}
                              </Space>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {a.account_name ? `账号 ${a.account_name} · ` : ''}
                                {a.provider ? `${a.provider} · ` : ''}
                                {a.actual !== null && a.actual !== undefined
                                  ? `实际 ${a.actual}` : ''}
                                {a.threshold_value !== null && a.threshold_value !== undefined
                                  ? ` / 阈值 ${a.threshold_value}` : ''}
                                {a.pct !== null && a.pct !== undefined ? ` · ${a.pct}%` : ''}
                              </Text>
                            </Space>
                          </List.Item>
                        )}
                      />
                    )}
                  </Card>
                  <Card
                    size="small"
                    title={
                      <Space>
                        本月账单 <Tag>{bills.length}</Tag>
                        {billsLastSync ? (
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            · 上次同步 {new Date(billsLastSync).toLocaleString()}
                          </Text>
                        ) : null}
                      </Space>
                    }
                    extra={
                      <Button
                        size="small" type="primary"
                        icon={<SyncOutlined spin={billsSyncing} />}
                        loading={billsSyncing}
                        onClick={() => syncBills()}
                      >
                        🔄 同步本月
                      </Button>
                    }
                  >
                    {bills.length === 0 ? (
                      <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本月暂无账单（请点击“🔄 同步本月”）" />
                    ) : (
                      <List
                        size="small"
                        dataSource={bills}
                        renderItem={(b: any) => (
                          <List.Item>
                            <Space direction="vertical" size={2}>
                              <Text>
                                {b.month || '—'} · ¥ {b.final_cost ?? b.amount ?? '—'}
                                {b.original_cost !== null && b.original_cost !== undefined
                                  ? ` (原始 ¥${b.original_cost})` : ''}
                              </Text>
                              <Space size={4}>
                                {b.provider ? <Tag color="blue">{b.provider}</Tag> : null}
                                {b.status ? <Tag>{b.status}</Tag> : null}
                              </Space>
                            </Space>
                          </List.Item>
                        )}
                      />
                    )}
                  </Card>
                </Space>
              ),
            },
            {
              key: 'history-bills',
              label: (<Space><ProfileOutlined />过往账单 <Tag color="cyan">{filteredHistoryBills.length}</Tag></Space>),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Card size="small">
                    <Space wrap>
                      <Space size={4}>
                        <Text type="secondary" style={{ fontSize: 12 }}>月份</Text>
                        <DatePicker
                          picker="month"
                          value={historyMonth}
                          onChange={(v) => {
                            setHistoryMonth(v);
                            setHistoryDate(null);
                            loadHistoryBills(v);
                          }}
                          allowClear
                          placeholder="选择月份"
                        />
                      </Space>
                      <Space size={4}>
                        <Text type="secondary" style={{ fontSize: 12 }}>日期</Text>
                        <DatePicker
                          value={historyDate}
                          onChange={(v) => setHistoryDate(v)}
                          allowClear
                          placeholder="可选：按天筛选"
                          disabledDate={(d) =>
                            historyMonth ? !d.isSame(historyMonth, 'month') : false
                          }
                        />
                      </Space>
                      <Space size={4}>
                        <Text type="secondary" style={{ fontSize: 12 }}>状态</Text>
                        <Select
                          style={{ width: 140 }}
                          value={historyStatus}
                          onChange={(v) => setHistoryStatus(v)}
                          allowClear
                          placeholder="全部状态"
                          options={[
                            { value: 'draft', label: 'draft 草稿' },
                            { value: 'confirmed', label: 'confirmed 已确认' },
                            { value: 'paid', label: 'paid 已支付' },
                          ]}
                        />
                      </Space>
                      <Button
                        size="small"
                        type="primary"
                        icon={<SyncOutlined spin={historySyncing} />}
                        loading={historySyncing}
                        onClick={syncHistoryBills}
                      >
                        🔄 同步{historyMonth ? historyMonth.format('YYYY-MM') : '本月'}
                      </Button>
                      <Button
                        size="small"
                        icon={<SyncOutlined />}
                        loading={historyLoading}
                        onClick={() => loadHistoryBills()}
                      >
                        刷新
                      </Button>
                    </Space>
                    {historyLastSync ? (
                      <div style={{ marginTop: 6 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          来源：本地 cc_bill · 上次同步 {new Date(historyLastSync).toLocaleString()}
                        </Text>
                      </div>
                    ) : (
                      <div style={{ marginTop: 6 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          来源：本地 cc_bill (未同步, 请点击 “🔄 同步” 按钮)
                        </Text>
                      </div>
                    )}
                  </Card>
                  {historyErr ? <Alert message={historyErr} type="warning" showIcon /> : null}
                  {historyLoading ? (
                    <Skeleton active />
                  ) : filteredHistoryBills.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        historyBills.length > 0
                          ? '当前筛选条件下无账单，尝试清除日期或状态筛选'
                          : '所选月份暂无账单记录'
                      }
                    />
                  ) : (
                    <Timeline
                      items={
                        Object.entries(
                          filteredHistoryBills.reduce((acc: Record<string, any[]>, b: any) => {
                            const key = (b.month || b.period || b.bill_date || 'unknown')
                              .toString().slice(0, 7);
                            (acc[key] = acc[key] || []).push(b);
                            return acc;
                          }, {})
                        )
                          .sort((a, b) => b[0].localeCompare(a[0]))
                          .map(([month, items]: [string, any]) => ({
                            color: 'blue',
                            children: (
                              <Space direction="vertical" size={2} style={{ width: '100%' }}>
                                <Text strong>{month}</Text>
                                {items.map((b: any, i: number) => (
                                  <Space key={i} size={6} wrap>
                                    <Text type="secondary" style={{ fontSize: 12 }}>
                                      {b.bill_date || b.date || b.period || month}
                                    </Text>
                                    <Text>¥ {b.amount ?? b.total_amount ?? '—'}</Text>
                                    {b.status ? (
                                      <Tag color={
                                        b.status === 'paid' ? 'green'
                                          : b.status === 'confirmed' ? 'blue'
                                            : 'default'
                                      }>{b.status}</Tag>
                                    ) : null}
                                  </Space>
                                ))}
                              </Space>
                            ),
                          }))
                      }
                    />
                  )}
                </Space>
              ),
            },
            {
              key: 'tickets',
              label: (
                <Space>
                  <CustomerServiceOutlined />
                  工单 <Tag color="orange">{tickets.length}</Tag>
                </Space>
              ),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  {/* 顶部 Statistic 卡片:总数/近30天/按状态 */}
                  {ticketStats && ticketStats.total > 0 && (
                    <Row gutter={12}>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic title="工单总数" value={ticketStats.total} />
                        </Card>
                      </Col>
                      <Col span={6}>
                        <Card size="small">
                          <Statistic
                            title="近 30 天新增"
                            value={ticketStats.last_30d_count}
                            valueStyle={{
                              color: ticketStats.last_30d_count > 0 ? '#fa8c16' : undefined,
                            }}
                          />
                        </Card>
                      </Col>
                      <Col span={12}>
                        <Card size="small" title="按状态分布" bodyStyle={{ padding: '12px 16px' }}>
                          <Space size={[8, 4]} wrap>
                            {Object.entries(ticketStats.by_status)
                              .sort((a, b) => b[1] - a[1])
                              .map(([status, count]) => {
                                const color =
                                  status === 'CLOSED' ? 'default' :
                                  status === 'IN_PROGRESS' ? 'processing' :
                                  status === 'OPEN' ? 'blue' :
                                  status === 'PENDING' ? 'gold' :
                                  status === 'RESOLVED' ? 'green' :
                                  status === 'UNKNOWN' ? 'default' : 'cyan';
                                return (
                                  <Tag key={status} color={color}>
                                    {status} · {count}
                                  </Tag>
                                );
                              })}
                            {Object.keys(ticketStats.by_status).length === 0 && (
                              <Text type="secondary">—</Text>
                            )}
                          </Space>
                        </Card>
                      </Col>
                    </Row>
                  )}
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      来源：本地镜像 (gongdan) · 匹配字段
                      <Tag style={{ marginLeft: 6 }} color="geekblue">customer_code</Tag>
                    </Text>
                    <Space>
                      <Button
                        size="small"
                        icon={<SyncOutlined spin={ticketsSyncing} />}
                        loading={ticketsSyncing}
                        onClick={syncTickets}
                      >
                        🔄 同步工单
                      </Button>
                      <Button
                        size="small"
                        icon={<SyncOutlined />}
                        loading={ticketsLoading}
                        onClick={loadTickets}
                      >
                        刷新
                      </Button>
                    </Space>
                  </Space>
                  <Table<LocalTicket>
                    size="small"
                    rowKey="id"
                    loading={ticketsLoading}
                    dataSource={tickets}
                    pagination={tickets.length > 10 ? { pageSize: 10, size: 'small' } : false}
                    locale={{
                      emptyText: (
                        <Empty
                          image={Empty.PRESENTED_IMAGE_SIMPLE}
                          description={
                            <Space direction="vertical" size={4}>
                              <Text>该客户暂无工单</Text>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                如果 gongdan 侧有新工单，点击「🔄 同步工单」拉取
                              </Text>
                            </Space>
                          }
                        />
                      ),
                    }}
                    columns={[
                      {
                        title: '工单编号', dataIndex: 'ticket_code', width: 170,
                        render: (v: string) => <code style={{ color: '#f97316' }}>{v}</code>,
                      },
                      {
                        title: '标题', dataIndex: 'title', ellipsis: true,
                        render: (v: string | null) => v || <Text type="secondary">—</Text>,
                      },
                      {
                        title: '状态', dataIndex: 'status', width: 110,
                        render: (s: string | null) => {
                          if (!s) return <Tag>—</Tag>;
                          const color =
                            s === 'CLOSED' ? 'default' :
                            s === 'IN_PROGRESS' ? 'processing' :
                            s === 'OPEN' ? 'blue' :
                            s === 'PENDING' ? 'gold' :
                            s === 'RESOLVED' ? 'green' : 'cyan';
                          return <Tag color={color}>{s}</Tag>;
                        },
                      },
                      {
                        title: '创建时间', dataIndex: 'created_at', width: 160,
                        render: (v: string | null) =>
                          v ? new Date(v).toLocaleString() : <Text type="secondary">—</Text>,
                      },
                    ]}
                  />
                </Space>
              ),
            },
            {
              key: 'resources',
              label: (
                <Space>
                  关联货源 <Tag color="blue">{resources.length}</Tag>
                </Space>
              ),
              children: (
                <>
                  <Space
                    style={{ marginBottom: 12, width: '100%', justifyContent: 'space-between' }}
                  >
                    <Text type="secondary">
                      来源：云管 cloudcost · 匹配字段
                      {matchField ? <Tag style={{ marginLeft: 6 }} color="geekblue">{matchField}</Tag> : null}
                    </Text>
                    <Button icon={<SyncOutlined />} size="small" onClick={loadResources} loading={loading}>
                      刷新
                    </Button>
                  </Space>

                  {loading ? (
                    <Skeleton active />
                  ) : resources.length === 0 ? (
                    <Empty
                      image={Empty.PRESENTED_IMAGE_SIMPLE}
                      description={
                        <Space direction="vertical" size={4}>
                          <Text>云管侧暂无匹配货源</Text>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            gongdan 客户编号 <code>{customer.customer_code}</code> 与云管 service-account.{matchField} 没有命中。<br />
                            可能需要在云管侧把该客户绑定到对应账号。
                          </Text>
                        </Space>
                      }
                    />
                  ) : (
                    <List
                      dataSource={resources}
                      renderItem={(r) => (
                        <List.Item>
                          <List.Item.Meta
                            avatar={
                              <Avatar
                                icon={<CloudServerOutlined />}
                                style={{ background: '#eef2ff', color: '#4f46e5' }}
                              />
                            }
                            title={
                              <Space>
                                <Text strong>{r.resource_name}</Text>
                                <Tag color={PROVIDER_COLOR[r.provider] || 'default'}>{r.provider}</Tag>
                                {r.status ? <Tag>{r.status}</Tag> : null}
                              </Space>
                            }
                            description={
                              <Space direction="vertical" size={2} style={{ fontSize: 12 }}>
                                <Text type="secondary">
                                  <LinkOutlined /> supply_source_id: {r.supply_source_id ?? '-'} · 供应商: {r.supplier_name ?? '-'}
                                </Text>
                                {r.external_project_id ? (
                                  <Text type="secondary" copyable={{ text: r.external_project_id }}>
                                    project: <code>{r.external_project_id}</code>
                                  </Text>
                                ) : null}
                              </Space>
                            }
                          />
                        </List.Item>
                      )}
                    />
                  )}
                </>
              ),
            },
          ]}
        />
      )}
      <Modal
        title="新建合同"
        open={contractModalOpen}
        onOk={submitContract}
        onCancel={() => setContractModalOpen(false)}
        confirmLoading={contractSaving}
        destroyOnClose
        okText="创建"
        cancelText="取消"
      >
        <Form form={contractForm} layout="vertical" initialValues={{ status: 'active' }}>
          <Form.Item name="contract_code" label="合同编号" rules={[{ required: true, message: '请输入合同编号' }]}>
            <Input placeholder="例: CN-2026-001" />
          </Form.Item>
          <Form.Item name="title" label="标题">
            <Input placeholder="合同标题" />
          </Form.Item>
          <Space style={{ display: 'flex', width: '100%' }} align="start">
            <Form.Item name="amount" label="金额" style={{ flex: 1 }}>
              <InputNumber style={{ width: '100%' }} min={0} precision={2} placeholder="¥" />
            </Form.Item>
            <Form.Item name="status" label="状态" style={{ flex: 1 }}>
              <Select options={[
                { value: 'active', label: '生效中' },
                { value: 'expired', label: '已过期' },
                { value: 'terminated', label: '已终止' },
              ]} />
            </Form.Item>
          </Space>
          <Space style={{ display: 'flex', width: '100%' }} align="start">
            <Form.Item name="start_date" label="开始日期" style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="end_date" label="结束日期" style={{ flex: 1 }}>
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
          </Space>
          <Form.Item name="notes" label="备注">
            <Input.TextArea rows={2} placeholder="合同备注" />
          </Form.Item>
        </Form>
      </Modal>
      <Modal
        title={currentSalesUser ? '再分配销售' : '分配销售'}
        open={assignOpen} onOk={submitAssign} onCancel={() => setAssignOpen(false)} destroyOnClose
      >
        <Form form={assignForm} layout="vertical">
          <Form.Item name="sales_user_id" label="分配给">
            <Select
              allowClear placeholder="留空=取消分配 / 退回商机池"
              showSearch optionFilterProp="label"
              options={salesUsers.filter((u: any) => u.is_active).map((u: any) => ({
                value: u.id,
                label: `${u.name}${u.email ? ' · ' + u.email : ''}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="reason" label="原因 (可选)">
            <Input.TextArea rows={2} placeholder="例：张三休假，临时转李四" />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
}

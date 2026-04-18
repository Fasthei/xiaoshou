import { useEffect, useMemo, useState } from 'react';
import {
  Drawer, Tabs, Descriptions, Tag, Space, Typography, List, Avatar, Empty,
  Skeleton, Button, Card, Timeline, Select, Input, Modal, Form, Table, Alert,
  Statistic, Row, Col, DatePicker, Tooltip, Collapse,
  Upload, InputNumber, Popconfirm,
  message as antdMessage,
} from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import {
  CloudServerOutlined, SyncOutlined, LinkOutlined, BulbOutlined,
  UserSwitchOutlined, HistoryOutlined, FileTextOutlined,
  ProfileOutlined, CustomerServiceOutlined,
  FullscreenOutlined, FullscreenExitOutlined,
  ZoomInOutlined, ZoomOutOutlined, CloseOutlined,
  UploadOutlined, DownloadOutlined,
  PaperClipOutlined,
  PlusOutlined, DeleteOutlined,
} from '@ant-design/icons';
import { STAGE_META, STAGE_ORDER } from '../constants/stage';
import dayjs, { Dayjs } from 'dayjs';
import { api } from '../api/axios';
import type { Customer } from '../types';
import HealthRadar from './HealthRadar';
import CustomerInsightPanel from './CustomerInsightPanel';
import CustomerProfileTab from './CustomerProfileTab';
import CustomerOrderWizardModal from './CustomerOrderWizardModal';

const { Text } = Typography;

interface LinkedResource {
  id: number;              // link id (customer_resource.id)
  resource_id: number;
  resource_code?: string | null;
  cloud_provider?: string | null;
  account_name?: string | null;
  identifier_field?: string | null;
  end_user_label?: string | null;
  created_at?: string | null;
}

interface AvailableResource {
  id: number;
  resource_code?: string | null;
  cloud_provider?: string | null;
  account_name?: string | null;
  identifier_field?: string | null;
}

const PROVIDER_COLOR: Record<string, string> = {
  aws: 'orange', azure: 'blue', gcp: 'red', aliyun: 'cyan',
  AWS: 'orange', AZURE: 'blue', GCP: 'red', ALIYUN: 'cyan', TAIJI: 'purple',
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
  const [resources, setResources] = useState<LinkedResource[]>([]);
  // 关联货源添加 Modal
  const [addOpen, setAddOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [availableResources, setAvailableResources] = useState<AvailableResource[]>([]);
  const [availableLoading, setAvailableLoading] = useState(false);
  const [picked, setPicked] = useState<React.Key[]>([]);
  const [resourceQ, setResourceQ] = useState('');
  const [providerFilter, setProviderFilter] = useState<string | undefined>(undefined);
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
  const [historyBills, setHistoryBills] = useState<any[]>([]);
  const [historyErr, setHistoryErr] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historySyncing, setHistorySyncing] = useState(false);
  const [historyLastSync, setHistoryLastSync] = useState<string | null>(null);
  const [historyMonth, setHistoryMonth] = useState<Dayjs | null>(dayjs());
  const [historyDate, setHistoryDate] = useState<Dayjs | null>(null);
  const [historyStatus, setHistoryStatus] = useState<string | undefined>(undefined);

  // --- Stage request / recycle state ---
  const [stageRequestOpen, setStageRequestOpen] = useState(false);
  const [stageRequestForm] = Form.useForm<{ to_stage: string; reason: string }>();
  const [stageRequestLoading, setStageRequestLoading] = useState(false);

  // 新建订单向导
  const [orderWizardOpen, setOrderWizardOpen] = useState(false);

  const loadTimeline = async () => {
    if (!customer) return;
    const [tl, sh] = await Promise.allSettled([
      api.get(`/api/customers/${customer.id}/timeline`),
      api.get(`/api/customers/${customer.id}/stage-history`),
    ]);
    const tlItems = tl.status === 'fulfilled' ? (Array.isArray(tl.value.data) ? tl.value.data : []) : [];
    const shRaw = sh.status === 'fulfilled' ? sh.value.data : [];
    const shItems = Array.isArray(shRaw) ? shRaw : shRaw?.items || [];
    const stageEvents = shItems.map((s: any) => ({
      kind: 'stage_change',
      at: s.decided_at || s.created_at,
      title: `Stage: ${s.from_stage} → ${s.to_stage}`,
      detail: s.reason,
      meta: { status: s.status, decided_by: s.decided_by },
    }));
    const merged = [...tlItems, ...stageEvents].sort((a: any, b: any) =>
      new Date(b.at).getTime() - new Date(a.at).getTime()
    );
    setTimeline(merged);
  };

  const submitStageRequest = async () => {
    if (!customer) return;
    const v = await stageRequestForm.validateFields();
    setStageRequestLoading(true);
    try {
      await api.post(`/api/customers/${customer.id}/stage/request`, v);
      antdMessage.success('Stage 变更申请已提交，等待主管审批');
      setStageRequestOpen(false);
      stageRequestForm.resetFields();
      loadTimeline();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '提交失败');
    } finally {
      setStageRequestLoading(false);
    }
  };


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
      const { data: created } = await api.post('/api/contracts', payload);
      // One-step: if user picked a file, upload immediately after create
      const fileList: UploadFile[] = Array.isArray(v.file) ? v.file : [];
      const fileObj: File | undefined = fileList[0]?.originFileObj as File | undefined;
      if (fileObj && created?.id) {
        const ok = await uploadContractFile(created.id, fileObj);
        if (!ok) {
          antdMessage.warning('合同已创建，但附件上传失败，请在列表中点「上传」重试');
        }
        // success toast emitted by uploadContractFile itself — avoid double toast
      } else {
        antdMessage.success('合同已创建');
      }
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
      setResources(Array.isArray(data) ? data : []);
    } catch (e) {
      setResources([]);
    } finally {
      setLoading(false);
    }
  };

  const loadAvailableResources = async () => {
    setAvailableLoading(true);
    try {
      const { data } = await api.get('/api/resources', { params: { page_size: 100 } });
      setAvailableResources((data?.items || []) as AvailableResource[]);
    } catch {
      setAvailableResources([]);
    } finally {
      setAvailableLoading(false);
    }
  };

  const openAddResources = () => {
    setPicked([]);
    setResourceQ('');
    setProviderFilter(undefined);
    setAddOpen(true);
    loadAvailableResources();
  };

  const saveAddResources = async () => {
    if (!customer || picked.length === 0) {
      setAddOpen(false);
      return;
    }
    setAdding(true);
    try {
      const { data } = await api.post(
        `/api/customers/${customer.id}/resources`,
        { resource_ids: picked.map((k) => Number(k)) },
      );
      antdMessage.success(
        `已关联 ${data?.created ?? 0} 条` + (data?.skipped ? `，跳过 ${data.skipped}` : ''),
      );
      setAddOpen(false);
      loadResources();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '添加失败');
    } finally {
      setAdding(false);
    }
  };

  const unlinkResource = async (linkId: number) => {
    if (!customer) return;
    try {
      await api.delete(`/api/customers/${customer.id}/resources/${linkId}`);
      antdMessage.success('已取消关联');
      loadResources();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '取消关联失败');
    }
  };

  // 过滤后的可选货源列表（已关联的剔除 + 搜索 + 厂商筛选）
  const filteredAvailable = useMemo(() => {
    const linkedIds = new Set(resources.map((r) => r.resource_id));
    const q = resourceQ.trim().toLowerCase();
    return availableResources.filter((r) => {
      if (linkedIds.has(r.id)) return false;
      if (providerFilter && r.cloud_provider !== providerFilter) return false;
      if (q) {
        const hay = `${r.account_name || ''} ${r.identifier_field || ''} ${r.resource_code || ''}`.toLowerCase();
        if (!hay.includes(q)) return false;
      }
      return true;
    });
  }, [availableResources, resources, resourceQ, providerFilter]);

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
      loadTimeline();
      loadAssign();
      loadContracts();
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
    try {
      await api.patch(`/api/customers/${customer.id}/assign`, v);
      antdMessage.success('分配已更新');
      setAssignOpen(false);
      loadAssign();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '分配更新失败');
    }
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
            size="small" type="primary"
            icon={<PlusOutlined />}
            onClick={() => setOrderWizardOpen(true)}
            title="为该客户新建订单（需销售主管审批）"
          >
            新建订单
          </Button>
          <Button
            size="small" type="default"
            onClick={() => { stageRequestForm.resetFields(); setStageRequestOpen(true); }}
            title="申请修改 stage（需主管审批）"
          >
            申请修改 Stage
          </Button>
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
                        formal: 'blue',
                        inactive: 'default', frozen: 'red',
                      };
                      const labelMap: Record<string, string> = {
                        active: '客户池', potential: '潜在', prospect: '潜在',
                        formal: '正式',
                        inactive: '停用', frozen: '冻结',
                      };
                      return <Tag color={colorMap[s] || 'default'}>{labelMap[s] || s}</Tag>;
                    })()}
                  </Descriptions.Item>
                  <Descriptions.Item label="生命周期 Stage">
                    {(() => {
                      const stage = customer.lifecycle_stage;
                      if (!stage) return <Tag color="default">—</Tag>;
                      const meta = STAGE_META[stage];
                      const stageTag = meta
                        ? <Tag color={meta.color}>{meta.emoji} {meta.label}</Tag>
                        : <Tag>{stage}</Tag>;
                      if (customer.recycled_from_stage) {
                        const fromMeta = STAGE_META[customer.recycled_from_stage] || { label: customer.recycled_from_stage, emoji: '' };
                        const tip = `从 ${fromMeta.emoji} ${fromMeta.label} 回流${customer.recycle_reason ? ` / 原因: ${customer.recycle_reason}` : ''}`;
                        return (
                          <Space size={4}>
                            {stageTag}
                            <Tooltip title={tip}>
                              <Tag color="orange" style={{ cursor: 'default' }}>🔄</Tag>
                            </Tooltip>
                          </Space>
                        );
                      }
                      return stageTag;
                    })()}
                  </Descriptions.Item>
                  {customer.source_label ? (
                    <Descriptions.Item label="来源">
                      <Tag color="magenta">{customer.source_label}</Tag>
                    </Descriptions.Item>
                  ) : null}
                  <Descriptions.Item label="当月消耗">{customer.current_month_consumption ?? 0}</Descriptions.Item>
                  <Descriptions.Item label="创建时间">{customer.created_at ? dayjs(customer.created_at).format('YYYY-MM-DD HH:mm:ss') : '-'}</Descriptions.Item>
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
                  items={timeline.map((e: any) => {
                    const isStageChange = e.kind === 'stage_change';
                    return {
                      color: isStageChange ? 'purple' : (e.color || 'blue'),
                      children: (
                        <Space direction="vertical" size={2}>
                          <Space wrap>
                            <Text strong>{e.title}</Text>
                            {isStageChange && e.meta?.status && (
                              <Tag color={e.meta.status === 'approved' ? 'green' : e.meta.status === 'rejected' ? 'red' : 'orange'}>
                                {e.meta.status === 'approved' ? '已批准' : e.meta.status === 'rejected' ? '已驳回' : '待审批'}
                              </Tag>
                            )}
                          </Space>
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            {e.at ? new Date(e.at).toLocaleString() : ''} · {isStageChange ? 'stage变更' : e.kind}
                            {isStageChange && e.meta?.decided_by ? ` · ${e.meta.decided_by}` : ''}
                          </Text>
                          {e.detail ? <Text>{e.detail}</Text> : null}
                        </Space>
                      ),
                    };
                  })}
                />
              ),
            },
            {
              key: 'assign',
              label: (
                <Space><UserSwitchOutlined />分配 {currentSalesUser ? <Tag color="geekblue">{currentSalesUser.name}</Tag> : <Tag>未分配</Tag>}</Space>
              ),
              children: (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Card size="small" title="🩺 健康分">
                    {health ? (
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
                    ) : <Skeleton active />}
                  </Card>
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
              children: (
                <Collapse
                  defaultActiveKey={['basic']}
                  items={[
                    {
                      key: 'basic',
                      label: '基本资料',
                      children: <CustomerProfileTab customerId={customer.id} />,
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
                          <Alert
                            type="info"
                            showIcon
                            message="合同在新建订单流程中创建，此处只查看与下载"
                          />
                          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
                            <Button size="small" icon={<SyncOutlined />} onClick={loadContracts} loading={contractsLoading}>
                              刷新
                            </Button>
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
                                title: '操作', width: 120, fixed: 'right' as const,
                                render: (_: any, r: any) =>
                                  r.file_url ? (
                                    <Button
                                      size="small"
                                      type="link"
                                      icon={<DownloadOutlined />}
                                      onClick={() => downloadContractFile(r.id)}
                                    >
                                      下载
                                    </Button>
                                  ) : (
                                    <Text type="secondary" style={{ fontSize: 12 }}>无附件</Text>
                                  ),
                              },
                            ]}
                          />
                        </Space>
                      ),
                    },
                    {
                      key: 'history-bills',
                      label: (
                        <Space>
                          <ProfileOutlined />
                          过往账单 <Tag color="cyan">{filteredHistoryBills.length}</Tag>
                        </Space>
                      ),
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
                  ]}
                />
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
                <Card
                  title={
                    <Space>
                      <CloudServerOutlined /> 已关联货源 <Tag>{resources.length}</Tag>
                    </Space>
                  }
                  extra={
                    <Space>
                      <Button icon={<SyncOutlined />} size="small" onClick={loadResources} loading={loading}>
                        刷新
                      </Button>
                      <Button type="primary" size="small" icon={<PlusOutlined />} onClick={openAddResources}>
                        添加货源
                      </Button>
                    </Space>
                  }
                >
                  {loading ? (
                    <Skeleton active />
                  ) : resources.length === 0 ? (
                    <Empty description="暂无关联货源, 点右上角添加" />
                  ) : (
                    <Row gutter={[12, 12]}>
                      {resources.map((r) => (
                        <Col xs={24} sm={12} md={8} key={r.id}>
                          <Card
                            size="small"
                            extra={
                              <Popconfirm
                                title="取消关联?"
                                onConfirm={() => unlinkResource(r.id)}
                                okText="取消关联"
                                cancelText="不取消"
                              >
                                <Button size="small" danger icon={<DeleteOutlined />} />
                              </Popconfirm>
                            }
                          >
                            <Space direction="vertical" size={0} style={{ width: '100%' }}>
                              <Space>
                                <Tag color={PROVIDER_COLOR[r.cloud_provider || ''] || 'default'}>
                                  {r.cloud_provider || '-'}
                                </Tag>
                                <Text strong>{r.account_name || '(未命名)'}</Text>
                              </Space>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                <LinkOutlined /> {r.identifier_field || r.resource_code || '-'}
                              </Text>
                              {r.end_user_label ? (
                                <Text type="secondary" style={{ fontSize: 12 }}>
                                  终端: {r.end_user_label}
                                </Text>
                              ) : null}
                            </Space>
                          </Card>
                        </Col>
                      ))}
                    </Row>
                  )}
                </Card>
              ),
            },
          ]}
        />
      )}
      <Modal
        title="选择要关联的货源"
        open={addOpen}
        onOk={saveAddResources}
        onCancel={() => setAddOpen(false)}
        width={720}
        confirmLoading={adding}
        okText={`确认添加 (${picked.length})`}
        destroyOnClose
      >
        <Space style={{ width: '100%', marginBottom: 12 }} wrap>
          <Input.Search
            placeholder="搜账号名/标识/货源编码"
            allowClear
            style={{ width: 260 }}
            onChange={(e) => setResourceQ(e.target.value)}
          />
          <Select
            placeholder="云厂商"
            allowClear
            style={{ width: 140 }}
            value={providerFilter}
            onChange={setProviderFilter}
            options={['AZURE', 'AWS', 'GCP', 'TAIJI', 'ALIYUN'].map((v) => ({ value: v, label: v }))}
          />
        </Space>
        <Table
          rowKey="id"
          size="small"
          loading={availableLoading}
          dataSource={filteredAvailable}
          rowSelection={{
            selectedRowKeys: picked,
            onChange: (keys) => setPicked(keys),
          }}
          columns={[
            {
              title: '厂商', dataIndex: 'cloud_provider', width: 90,
              render: (p: string) => (
                <Tag color={PROVIDER_COLOR[p || ''] || 'default'}>{p || '-'}</Tag>
              ),
            },
            { title: '账号', dataIndex: 'account_name', render: (v: string) => v || '(未命名)' },
            { title: '标识', dataIndex: 'identifier_field', ellipsis: true,
              render: (v: string, r: any) => v || r.resource_code || '-' },
          ]}
          pagination={{ pageSize: 10, size: 'small' }}
        />
      </Modal>
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
          <Form.Item
            name="file"
            label="合同附件"
            valuePropName="fileList"
            getValueFromEvent={(e: any) => Array.isArray(e) ? e : e && e.fileList}
            extra="可选，支持 PDF / Word / JPG / PNG，单文件 ≤ 10MB"
          >
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
            >
              <Button icon={<UploadOutlined />}>选择文件（可选）</Button>
            </Upload>
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

      {/* Stage 变更申请 Modal */}
      <Modal
        title="申请修改 Stage"
        open={stageRequestOpen}
        onOk={submitStageRequest}
        onCancel={() => setStageRequestOpen(false)}
        confirmLoading={stageRequestLoading}
        destroyOnClose
        okText="提交申请"
        cancelText="取消"
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
          message="申请提交后需主管审批方可生效"
        />
        <Form form={stageRequestForm} layout="vertical">
          <Form.Item name="to_stage" label="目标 Stage" rules={[{ required: true, message: '请选择目标 Stage' }]}>
            <Select
              placeholder="选择要切换到的 Stage"
              options={STAGE_ORDER.map((key) => ({
                value: key,
                label: `${STAGE_META[key].emoji} ${STAGE_META[key].label}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="reason" label="申请原因" rules={[{ required: true, message: '请填写原因' }]}>
            <Input.TextArea rows={3} placeholder="说明此次 stage 变更的原因…" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 新建订单向导（已有客户，跳过客户信息步骤） */}
      {customer && (
        <CustomerOrderWizardModal
          open={orderWizardOpen}
          onClose={() => setOrderWizardOpen(false)}
          initialCustomer={{ id: customer.id, customer_name: customer.customer_name, customer_code: customer.customer_code }}
        />
      )}
    </Drawer>
  );
}

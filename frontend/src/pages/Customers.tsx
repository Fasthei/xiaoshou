import { useEffect, useMemo, useState } from 'react';
import {
  Button, Card, Dropdown, Form, Input, Modal, Segmented, Select, Space, Table, Tag, Tooltip, Typography,
  message as antdMessage,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, SyncOutlined,
  EyeOutlined, EditOutlined, DownloadOutlined, UploadOutlined, DownOutlined,
  DeleteOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import { Upload } from 'antd';
import { api } from '../api/axios';
import type { Customer, Pagination } from '../types';
import CustomerDetailDrawer from '../components/CustomerDetailDrawer';
import CustomerOrderWizardModal from '../components/CustomerOrderWizardModal';
import { STAGE_META } from '../constants/stage';
const { Title } = Typography;

const FORM_STATUS_OPTIONS = [
  { value: 'potential', label: '潜在客户' },
  { value: 'active', label: '客户池' },
  { value: 'formal', label: '正式客户（工单系统同步自动设置）', disabled: true },
];

// lifecycle_stage → group mapping
const STAGE_GROUP: Record<string, 'active' | 'contacting' | 'lead'> = {
  active: 'active',
  contacting: 'contacting',
  lead: 'lead',
};

type GroupKey = 'active' | 'contacting' | 'lead';

const GROUP_META: Record<GroupKey, { label: string; emoji: string }> = {
  active:     { label: '正式客户', emoji: '🎯' },
  contacting: { label: '跟进客户', emoji: '📞' },
  lead:       { label: '商机池',  emoji: '🧊' },
};

export default function Customers() {
  const [allData, setAllData] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [onlyUnassigned, setOnlyUnassigned] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<Customer>();
  const [editing, setEditing] = useState<Customer | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [detail, setDetail] = useState<Customer | null>(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [group, setGroup] = useState<GroupKey>('active');

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Pagination<Customer>>('/api/customers', {
        params: { page: 1, page_size: 100, keyword: keyword || undefined },
      });
      const list = Array.isArray(data?.items) ? data.items : [];
      const items = onlyUnassigned ? list.filter((c) => c.sales_user_id == null) : list;
      setAllData(items);
      setTotal(onlyUnassigned ? items.length : (data?.total ?? items.length));
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '加载客户列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    /* eslint-disable-next-line */
  }, []);

  // Filtered data by selected group
  const filteredData = useMemo(() => {
    return allData.filter((c) => {
      const g = STAGE_GROUP[c.lifecycle_stage || 'lead'] || 'lead';
      return g === group;
    });
  }, [allData, group]);

  const onSubmit = async () => {
    const v = await form.validateFields();
    if (editing) {
      await api.put(`/api/customers/${editing.id}`, v);
    } else {
      const customer_code = 'CUST-' + Math.random().toString(36).slice(2, 10).toUpperCase();
      await api.post('/api/customers', { ...v, customer_code });
    }
    setOpen(false); setEditing(null); form.resetFields();
    load();
  };

  const syncFromTicket = async () => {
    setSyncing(true);
    try {
      const { data } = await api.post('/api/sync/customers/from-ticket');
      antdMessage.success(`同步完成：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`);
      load();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '从工单同步失败');
    } finally {
      setSyncing(false);
    }
  };

  const segmentedOptions = (['active', 'contacting', 'lead'] as GroupKey[]).map((key) => {
    const { label, emoji } = GROUP_META[key];
    return {
      value: key,
      label: `${emoji} ${label}`,
    };
  });

  const columns = [
    { title: '编号', dataIndex: 'customer_code', width: 160,
      render: (v: string) => <code style={{ color: '#0078D4' }}>{v}</code> },
    { title: '名称', dataIndex: 'customer_name',
      render: (v: string, r: Customer) => {
        const isRecycled = !!r.recycled_from_stage;
        const fromMeta = r.recycled_from_stage
          ? (STAGE_META[r.recycled_from_stage] || { label: r.recycled_from_stage, emoji: '' })
          : null;
        const tip = fromMeta
          ? `从 ${fromMeta.emoji} ${fromMeta.label} 回流${r.recycle_reason ? ` · 原因: ${r.recycle_reason}` : ''}`
          : '';
        return (
          <Space size={4}>
            <span
              style={{
                width: 28, height: 28, borderRadius: 4,
                background: '#DEECF9',
                display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                color: '#0078D4', fontSize: 12, fontWeight: 600,
              }}
            >
              {v?.[0] || '-'}
            </span>
            <span>{v}</span>
            {isRecycled && (
              <Tooltip title={tip}>
                <Tag color="orange" style={{ cursor: 'default', marginLeft: 2 }}>🔄</Tag>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    { title: '行业', dataIndex: 'industry', width: 100 },
    { title: '地区', dataIndex: 'region', width: 100 },
    {
      title: '来源', dataIndex: 'source_system', width: 160,
      render: (v: string, r: Customer) => (
        <Space size={4} wrap>
          {v ? <Tag color="geekblue">{v}</Tag> : <Tag>手工</Tag>}
          {r.source_label ? <Tag color="magenta">{r.source_label}</Tag> : null}
        </Space>
      ),
    },
    { title: '当月消耗', dataIndex: 'current_month_consumption', width: 110 },
    {
      title: '销售', dataIndex: 'sales_user_name', width: 110,
      render: (v: string | null | undefined) => v
        ? <Tag color="blue">{v}</Tag>
        : <span style={{ color: '#6B7280' }}>—</span>,
    },
    {
      title: '操作', width: 240, fixed: 'right' as const,
      render: (_: unknown, r: Customer) => {
        const isLead = (r.lifecycle_stage || 'lead') === 'lead';
        return (
          <Space size={4}>
            <Button size="small" type="link" icon={<EyeOutlined />}
              onClick={() => setDetail(r)}>详情</Button>
            <Button size="small" type="link" icon={<EditOutlined />}
              onClick={() => { setEditing(r); form.setFieldsValue(r); setOpen(true); }}>编辑</Button>
            <Tooltip title={isLead
              ? '彻底删除（档案保留, 工单同名不复活）'
              : '仅允许在商机池 lead 阶段删除；正式/跟进客户请先退回商机池'}>
              <Button
                size="small" type="link" danger
                icon={<DeleteOutlined />}
                disabled={!isLead}
                onClick={() => confirmHardDelete(r)}
              >删除</Button>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  // 议题 B：商机池彻底删除（is_deleted=true，档案保留）
  const confirmHardDelete = (c: Customer) => {
    let reason = '';
    Modal.confirm({
      title: <Space><ExclamationCircleOutlined style={{ color: '#cf1322' }} /><span>彻底删除客户</span></Space>,
      icon: null,
      content: (
        <div>
          <p style={{ marginTop: 0 }}>
            即将彻底删除：<b>{c.customer_name}</b>{c.customer_code ? <Tag style={{ marginLeft: 8 }}>{c.customer_code}</Tag> : null}
          </p>
          <ul style={{ paddingLeft: 18, color: '#6B7280', fontSize: 12 }}>
            <li>客户列表不再显示，但档案（关联货源 / 订单 / 账单）仍可查</li>
            <li>若工单系统以后又同名拉回来，<b>不会</b>自动复活（命中墓碑）</li>
          </ul>
          <Input.TextArea
            rows={2} placeholder="删除原因（可选, 用于审计）"
            maxLength={200} showCount
            onChange={(e) => { reason = e.target.value; }}
          />
        </div>
      ),
      okText: '确认彻底删除', okButtonProps: { danger: true },
      cancelText: '取消',
      onOk: async () => {
        try {
          await api.post(`/api/customers/${c.id}/hard-delete`, { reason: reason || null });
          antdMessage.success('客户已彻底删除，档案保留');
          load();
        } catch (e: any) {
          antdMessage.error(
            '删除失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'),
          );
          throw e;   // 让 Modal 不关闭
        }
      },
    });
  };

  return (
    <div className="page-fade">
      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 12, width: '100%', justifyContent: 'space-between' }} wrap>
          <Title level={4} style={{ margin: 0 }}>客户管理</Title>
          <Space wrap>
            <Input
              placeholder="名称/编号搜索"
              allowClear
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onPressEnter={() => load()}
              style={{ width: 220 }}
            />
            <Button
              type={onlyUnassigned ? 'primary' : 'default'}
              onClick={() => { setOnlyUnassigned(!onlyUnassigned); setTimeout(load, 0); }}
            >
              {onlyUnassigned ? '✓ 只看未分配' : '只看未分配'}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={() => load()}>刷新</Button>
            <Button icon={<DownloadOutlined />} onClick={async () => {
              const resp = await fetch('/api/customers/bulk/export.csv', {
                headers: {
                  Authorization: `Bearer ${localStorage.getItem('token') || sessionStorage.getItem('token') || ''}`,
                },
              });
              if (!resp.ok) { antdMessage.error('导出失败'); return; }
              const blob = await resp.blob();
              const url = URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `customers-${new Date().toISOString().slice(0, 10)}.csv`;
              a.click();
              URL.revokeObjectURL(url);
            }}>导出CSV</Button>
            <Upload
              accept=".csv"
              showUploadList={false}
              beforeUpload={async (file) => {
                const fd = new FormData();
                fd.append('file', file);
                try {
                  const { data } = await api.post('/api/customers/bulk/import.csv', fd, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                  });
                  antdMessage.success(
                    `导入完成: 新增 ${data.created} · 更新 ${data.updated} · 跳过 ${data.skipped}`
                  );
                  load();
                } catch (e: any) {
                  antdMessage.error(e?.response?.data?.detail || '导入失败');
                }
                return false;
              }}
            >
              <Button icon={<UploadOutlined />}>导入CSV</Button>
            </Upload>
            <Button icon={<SyncOutlined spin={syncing} />} onClick={syncFromTicket} loading={syncing}>
              从工单同步
            </Button>
            <Dropdown
              trigger={['click']}
              menu={{
                items: [
                  {
                    key: 'customer-only',
                    label: '新建客户（空客户）',
                    onClick: () => { setEditing(null); form.resetFields(); setOpen(true); },
                  },
                  {
                    key: 'customer-plus-order',
                    label: '新建客户 + 新建订单',
                    onClick: () => { setWizardOpen(true); },
                  },
                ],
              }}
            >
              <Button type="primary" icon={<PlusOutlined />}>
                新建客户 <DownOutlined />
              </Button>
            </Dropdown>
          </Space>
        </Space>

        <div style={{ marginBottom: 16 }}>
          <Segmented
            value={group}
            onChange={(v) => setGroup(v as GroupKey)}
            options={segmentedOptions}
            size="middle"
          />
        </div>

        <Table<Customer>
          rowKey="id"
          loading={loading}
          columns={columns}
          dataSource={filteredData}
          scroll={{ x: 1200 }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
          }}
        />

        <Modal
          open={open} onOk={onSubmit} onCancel={() => { setOpen(false); setEditing(null); }}
          title={editing ? `编辑客户 #${editing.id}` : '新建客户'}
          destroyOnClose width={560}
        >
          <Form form={form} layout="vertical">
            <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="customer_short_name" label="简称"><Input /></Form.Item>
            <Form.Item name="industry" label="行业"><Input /></Form.Item>
            <Form.Item name="region" label="地区"><Input /></Form.Item>
            <Form.Item name="customer_status" label="状态" rules={[{ required: true }]} initialValue="potential"
              tooltip="新建默认为潜在客户; 需要推进时改为客户池; 正式客户由工单系统同步自动设置, 用户不能手动选">
              <Select
                options={FORM_STATUS_OPTIONS}
                disabled={editing?.customer_status === 'formal'}
              />
            </Form.Item>
            <Form.Item name="source_label" label="来源"
              tooltip="该客户从哪里来的? 如 朋友推荐 / 展会 / 老带新">
              <Input placeholder="如: 朋友推荐 / 展会 / 老带新 / CSV 导入" maxLength={50} />
            </Form.Item>
          </Form>
        </Modal>
      </Card>

      <CustomerDetailDrawer
        open={!!detail} customer={detail} onClose={() => setDetail(null)}
      />

      <CustomerOrderWizardModal
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onSuccess={() => { setWizardOpen(false); load(); }}
      />
    </div>
  );
}

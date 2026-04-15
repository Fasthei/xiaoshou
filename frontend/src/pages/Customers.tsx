import { useEffect, useState } from 'react';
import {
  Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography,
  message as antdMessage,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, SearchOutlined, SyncOutlined,
  EyeOutlined, EditOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Customer, Pagination } from '../types';
import CustomerDetailDrawer from '../components/CustomerDetailDrawer';

const { Title } = Typography;

const STATUS_COLOR: Record<string, string> = {
  active: 'green', inactive: 'default', frozen: 'red', prospect: 'blue',
};

export default function Customers() {
  const [data, setData] = useState<Customer[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState<string | undefined>();
  const [onlyUnassigned, setOnlyUnassigned] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<Customer>();
  const [editing, setEditing] = useState<Customer | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [detail, setDetail] = useState<Customer | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Pagination<Customer>>('/api/customers', {
        params: { page, page_size: pageSize, keyword: keyword || undefined, customer_status: status },
      });
      const items = onlyUnassigned ? data.items.filter((c) => c.sales_user_id == null) : data.items;
      setData(items);
      setTotal(onlyUnassigned ? items.length : data.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, pageSize]);

  const onSubmit = async () => {
    const v = await form.validateFields();
    if (editing) {
      await api.put(`/api/customers/${editing.id}`, v);
    } else {
      await api.post('/api/customers', v);
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
    } finally {
      setSyncing(false);
    }
  };

  const columns = [
    { title: '编号', dataIndex: 'customer_code', width: 160,
      render: (v: string) => <code style={{ color: '#4f46e5' }}>{v}</code> },
    { title: '名称', dataIndex: 'customer_name',
      render: (v: string, r: Customer) => (
        <Space>
          <span
            style={{
              width: 28, height: 28, borderRadius: 8,
              background: 'linear-gradient(135deg, #4f46e5, #ec4899)',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              color: 'white', fontSize: 12, fontWeight: 600,
            }}
          >
            {v?.[0] || '-'}
          </span>
          <span>{v}</span>
        </Space>
      ),
    },
    { title: '行业', dataIndex: 'industry', width: 100 },
    { title: '地区', dataIndex: 'region', width: 100 },
    {
      title: '状态', dataIndex: 'customer_status', width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    {
      title: '来源', dataIndex: 'source_system', width: 110,
      render: (v: string) => v
        ? <Tag color="geekblue">{v}</Tag>
        : <Tag>手工</Tag>,
    },
    { title: '当月消耗', dataIndex: 'current_month_consumption', width: 110 },
    {
      title: '操作', width: 150, fixed: 'right' as const,
      render: (_: unknown, r: Customer) => (
        <Space size={4}>
          <Button size="small" type="link" icon={<EyeOutlined />}
            onClick={() => setDetail(r)}>详情</Button>
          <Button size="small" type="link" icon={<EditOutlined />}
            onClick={() => { setEditing(r); form.setFieldsValue(r); setOpen(true); }}>编辑</Button>
        </Space>
      ),
    },
  ];

  return (
    <div className="page-fade">
      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
          <Title level={4} style={{ margin: 0 }}>客户管理</Title>
          <Space wrap>
            <Input
              placeholder="名称/编号搜索"
              allowClear
              prefix={<SearchOutlined />}
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onPressEnter={() => { setPage(1); load(); }}
              style={{ width: 220 }}
            />
            <Select
              placeholder="状态"
              allowClear style={{ width: 120 }}
              value={status}
              onChange={(v) => { setStatus(v); setPage(1); load(); }}
              options={['active', 'inactive', 'frozen', 'prospect'].map((v) => ({ value: v, label: v }))}
            />
            <Button
              type={onlyUnassigned ? 'primary' : 'default'}
              onClick={() => { setOnlyUnassigned(!onlyUnassigned); setPage(1); setTimeout(load, 0); }}
            >
              {onlyUnassigned ? '✓ 只看未分配' : '只看未分配'}
            </Button>
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
            <Button icon={<SyncOutlined spin={syncing} />} onClick={syncFromTicket} loading={syncing}>
              从工单同步
            </Button>
            <Button type="primary" icon={<PlusOutlined />}
              onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>
              新建客户
            </Button>
          </Space>
        </Space>

        <Table<Customer>
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
        />

        <Modal
          open={open} onOk={onSubmit} onCancel={() => { setOpen(false); setEditing(null); }}
          title={editing ? `编辑客户 #${editing.id}` : '新建客户'}
          destroyOnClose width={560}
        >
          <Form form={form} layout="vertical">
            <Form.Item name="customer_code" label="客户编号" rules={[{ required: true }]}>
              <Input disabled={!!editing} />
            </Form.Item>
            <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
              <Input />
            </Form.Item>
            <Form.Item name="customer_short_name" label="简称"><Input /></Form.Item>
            <Form.Item name="industry" label="行业"><Input /></Form.Item>
            <Form.Item name="region" label="地区"><Input /></Form.Item>
            <Form.Item name="customer_status" label="状态" rules={[{ required: true }]} initialValue="active">
              <Select options={['active', 'inactive', 'frozen', 'prospect'].map((v) => ({ value: v, label: v }))} />
            </Form.Item>
          </Form>
        </Modal>
      </Card>

      <CustomerDetailDrawer
        open={!!detail} customer={detail} onClose={() => setDetail(null)}
      />
    </div>
  );
}

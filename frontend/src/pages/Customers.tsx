import { useEffect, useState } from 'react';
import {
  Button, Card, Form, Input, Modal, Select, Space, Table, Tag, Typography, Popconfirm,
} from 'antd';
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { Customer, Pagination } from '../types';

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
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<Customer>();
  const [editing, setEditing] = useState<Customer | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Pagination<Customer>>('/api/customers', {
        params: { page, page_size: pageSize, keyword: keyword || undefined, customer_status: status },
      });
      setData(data.items);
      setTotal(data.total);
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

  const columns = [
    { title: '编号', dataIndex: 'customer_code', width: 140 },
    { title: '名称', dataIndex: 'customer_name' },
    { title: '简称', dataIndex: 'customer_short_name', width: 120 },
    { title: '行业', dataIndex: 'industry', width: 100 },
    { title: '地区', dataIndex: 'region', width: 100 },
    {
      title: '状态', dataIndex: 'customer_status', width: 100,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
    { title: '当月消耗', dataIndex: 'current_month_consumption', width: 120 },
    {
      title: '操作', width: 120, fixed: 'right' as const,
      render: (_: unknown, r: Customer) => (
        <Button type="link" onClick={() => { setEditing(r); form.setFieldsValue(r); setOpen(true); }}>
          编辑
        </Button>
      ),
    },
  ];

  return (
    <Card>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>客户管理</Title>
        <Space>
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
            allowClear
            style={{ width: 120 }}
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); load(); }}
            options={['active', 'inactive', 'frozen', 'prospect'].map((v) => ({ value: v, label: v }))}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => { setEditing(null); form.resetFields(); setOpen(true); }}>
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
          <Form.Item name="customer_status" label="状态" rules={[{ required: true }]}
            initialValue="active">
            <Select options={['active', 'inactive', 'frozen', 'prospect'].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}

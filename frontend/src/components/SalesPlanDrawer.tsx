import { useEffect, useMemo, useState } from 'react';
import {
  Drawer, Tabs, Timeline, Button, Space, Empty, Form, Input, Modal, DatePicker,
  Select, Tag, Popconfirm, message as antdMessage, Typography, Spin,
} from 'antd';
import {
  PlusOutlined, EditOutlined, DeleteOutlined, CheckCircleOutlined,
  ClockCircleOutlined, PlayCircleOutlined, CloseCircleOutlined,
} from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { api } from '../api/axios';

const { Text, Paragraph } = Typography;

interface SalesUserLite {
  id: number;
  name: string;
}

interface SalesPlan {
  id: number;
  user_id: number;
  plan_date: string;
  plan_type: 'daily' | 'weekly' | 'monthly';
  title: string | null;
  content: string | null;
  status: 'pending' | 'in_progress' | 'done' | 'cancelled';
  created_at: string;
  updated_at?: string | null;
}

interface Props {
  user: SalesUserLite | null;
  open: boolean;
  onClose: () => void;
}

const STATUS_META: Record<SalesPlan['status'], { color: string; label: string; icon: JSX.Element }> = {
  pending: { color: 'default', label: '待办', icon: <ClockCircleOutlined /> },
  in_progress: { color: 'processing', label: '进行中', icon: <PlayCircleOutlined /> },
  done: { color: 'success', label: '已完成', icon: <CheckCircleOutlined /> },
  cancelled: { color: 'error', label: '已取消', icon: <CloseCircleOutlined /> },
};

export default function SalesPlanDrawer({ user, open, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'daily' | 'weekly' | 'monthly'>('daily');
  const [plans, setPlans] = useState<SalesPlan[]>([]);
  const [loading, setLoading] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<SalesPlan | null>(null);
  const [form] = Form.useForm<{
    plan_date: Dayjs;
    plan_type: 'daily' | 'weekly' | 'monthly';
    title?: string;
    content?: string;
    status: SalesPlan['status'];
  }>();

  const load = async () => {
    if (!user) return;
    setLoading(true);
    try {
      const { data } = await api.get<SalesPlan[]>('/api/sales/plans', {
        params: { user_id: user.id, plan_type: activeTab },
      });
      setPlans(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open && user) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, user?.id, activeTab]);

  const openNew = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      plan_type: activeTab,
      status: 'pending',
      plan_date: dayjs(),
    });
    setFormOpen(true);
  };

  const openEdit = (p: SalesPlan) => {
    setEditing(p);
    form.setFieldsValue({
      plan_type: p.plan_type,
      status: p.status,
      plan_date: dayjs(p.plan_date),
      title: p.title || undefined,
      content: p.content || undefined,
    });
    setFormOpen(true);
  };

  const submit = async () => {
    if (!user) return;
    const v = await form.validateFields();
    const body = {
      user_id: user.id,
      plan_date: v.plan_date.format('YYYY-MM-DD'),
      plan_type: v.plan_type,
      title: v.title || null,
      content: v.content || null,
      status: v.status,
    };
    if (editing) {
      await api.patch(`/api/sales/plans/${editing.id}`, body);
      antdMessage.success('已更新');
    } else {
      await api.post('/api/sales/plans', body);
      antdMessage.success('已创建');
    }
    setFormOpen(false);
    load();
  };

  const remove = async (p: SalesPlan) => {
    await api.delete(`/api/sales/plans/${p.id}`);
    antdMessage.success('已删除');
    load();
  };

  const sorted = useMemo(
    () => [...plans].sort((a, b) => (a.plan_date < b.plan_date ? 1 : -1)),
    [plans]
  );

  const timelineItems = sorted.map((p) => {
    const meta = STATUS_META[p.status];
    return {
      color: meta.color === 'default' ? 'gray' : meta.color,
      dot: meta.icon,
      children: (
        <Space direction="vertical" size={4} style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>{p.plan_date}</Text>
            <Tag color={meta.color}>{meta.label}</Tag>
            {p.title && <Text>{p.title}</Text>}
          </Space>
          {p.content && (
            <Paragraph style={{ marginBottom: 4, whiteSpace: 'pre-wrap' }}>
              {p.content}
            </Paragraph>
          )}
          <Space size={4}>
            <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(p)}>
              编辑
            </Button>
            <Popconfirm title="删除该计划？" onConfirm={() => remove(p)}>
              <Button size="small" danger icon={<DeleteOutlined />}>
                删除
              </Button>
            </Popconfirm>
          </Space>
        </Space>
      ),
    };
  });

  return (
    <Drawer
      title={user ? `${user.name} · 工作计划` : '工作计划'}
      open={open}
      onClose={onClose}
      width={560}
      destroyOnClose
      extra={
        <Button type="primary" icon={<PlusOutlined />} onClick={openNew}>
          新建计划
        </Button>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as any)}
        items={[
          { key: 'daily', label: '日计划' },
          { key: 'weekly', label: '周计划' },
          { key: 'monthly', label: '月计划' },
        ]}
      />
      {loading ? (
        <div style={{ textAlign: 'center', padding: 32 }}>
          <Spin />
        </div>
      ) : timelineItems.length === 0 ? (
        <Empty description="暂无计划，点右上角新建" />
      ) : (
        <Timeline items={timelineItems} style={{ marginTop: 16 }} />
      )}

      <Modal
        title={editing ? '编辑计划' : '新建计划'}
        open={formOpen}
        onOk={submit}
        onCancel={() => setFormOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical" preserve={false}>
          <Form.Item
            name="plan_type" label="类型" rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'daily', label: '日计划' },
                { value: 'weekly', label: '周计划' },
                { value: 'monthly', label: '月计划' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="plan_date" label="基准日期" rules={[{ required: true }]}
            tooltip="日计划=当日; 周计划=周一; 月计划=当月1号"
          >
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="title" label="标题">
            <Input placeholder="例: 拜访华东3家能源客户" maxLength={200} />
          </Form.Item>
          <Form.Item name="content" label="内容">
            <Input.TextArea rows={4} placeholder="计划详情..." />
          </Form.Item>
          <Form.Item name="status" label="状态" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'pending', label: '待办' },
                { value: 'in_progress', label: '进行中' },
                { value: 'done', label: '已完成' },
                { value: 'cancelled', label: '已取消' },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>
    </Drawer>
  );
}

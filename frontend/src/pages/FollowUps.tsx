import { useEffect, useState, useCallback } from 'react';
import {
  Card, Space, Typography, Select, Button, Table, Tag, message,
  Modal, Form, Input, Tabs, Badge,
} from 'antd';
import { ReloadOutlined, MessageOutlined, SwapOutlined, InboxOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api, getCurrentRoles } from '../api/axios';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;
const { TextArea } = Input;

interface FollowUpItem {
  id: number;
  customer_id: number;
  customer_code: string;
  customer_name: string;
  follow_type: string;
  title: string;
  content: string | null;
  outcome: string | null;
  next_action_date: string | null;
  created_at: string;
  operator_casdoor_id: string | null;
  to_sales_user_id: number | null;
  parent_follow_up_id: number | null;
  from_sales_name: string | null;
  to_sales_name: string | null;
}

interface CustomerOption {
  value: number;
  label: string;
}

interface SalesUser {
  id: number;
  name: string;
  casdoor_user_id: string | null;
}

const DAYS_OPTIONS = [
  { value: 7, label: '近 7 天' },
  { value: 30, label: '近 30 天' },
  { value: 90, label: '近 90 天' },
  { value: 180, label: '近 180 天' },
];

const TYPE_COLOR: Record<string, string> = {
  call: 'blue',
  meeting: 'green',
  email: 'orange',
  wechat: 'cyan',
  note: 'default',
  other: 'purple',
  comment: 'geekblue',
};

function isSalesOnly(roles: string[]): boolean {
  return !roles.includes('sales-manager') && !roles.includes('admin');
}

export default function FollowUps() {
  const { user } = useAuth();
  const roles = user?.roles ?? [];
  const salesOnly = isSalesOnly(roles);
  const canReassign = (() => {
    const r = getCurrentRoles();
    return r.includes('sales-manager') || r.includes('admin') || r.includes('root');
  })();

  // --- List tab state ---
  const [items, setItems] = useState<FollowUpItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [days, setDays] = useState(30);
  const [customerId, setCustomerId] = useState<number | undefined>(undefined);
  const [customerOptions, setCustomerOptions] = useState<CustomerOption[]>([]);
  const [loading, setLoading] = useState(false);

  // --- Inbox tab state ---
  const [inboxItems, setInboxItems] = useState<FollowUpItem[]>([]);
  const [inboxLoading, setInboxLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<'list' | 'inbox'>('list');

  // --- Sales user state ---
  const [salesUsers, setSalesUsers] = useState<SalesUser[]>([]);
  const [mySalesUserId, setMySalesUserId] = useState<number | undefined>(undefined);
  // null = all; number = specific; undefined = not yet initialized
  const [salesUserFilter, setSalesUserFilter] = useState<number | null | undefined>(undefined);

  // --- Comment modal ---
  const [commentOpen, setCommentOpen] = useState(false);
  const [commentTarget, setCommentTarget] = useState<FollowUpItem | null>(null);
  const [commentReplyTo, setCommentReplyTo] = useState<FollowUpItem | null>(null); // for reply
  const [commentForm] = Form.useForm<{ content: string; to_sales_user_id?: number }>();
  const [commentLoading, setCommentLoading] = useState(false);

  // --- Reassign modal ---
  const [reassignOpen, setReassignOpen] = useState(false);
  const [reassignTarget, setReassignTarget] = useState<FollowUpItem | null>(null);
  const [reassignForm] = Form.useForm<{ sales_user_id: number }>();
  const [reassignLoading, setReassignLoading] = useState(false);

  // Load sales users, detect current user's sales_user id
  useEffect(() => {
    api.get<SalesUser[]>('/api/sales/users')
      .then(res => {
        const users = res.data ?? [];
        setSalesUsers(users);
        if (user) {
          const matched = users.find(u => u.casdoor_user_id === user.sub)
            ?? users.find(u => u.name === user.name);
          if (matched) {
            setMySalesUserId(matched.id);
            setSalesUserFilter(salesOnly ? matched.id : null);
          } else {
            setSalesUserFilter(null);
          }
        } else {
          setSalesUserFilter(null);
        }
      })
      .catch(() => { setSalesUserFilter(null); });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.sub]);

  const loadList = useCallback(async () => {
    if (salesUserFilter === undefined) return; // not yet initialized
    setLoading(true);
    try {
      const params: Record<string, string | number> = { days, page, page_size: pageSize };
      if (salesUserFilter !== null) params.sales_user_id = salesUserFilter;
      if (customerId !== undefined) params.customer_id = customerId;
      const res = await api.get('/api/follow-ups', { params });
      setItems(res.data.items ?? []);
      setTotal(res.data.total ?? 0);
    } catch {
      message.error('加载跟进记录失败');
    } finally {
      setLoading(false);
    }
  }, [days, page, pageSize, customerId, salesUserFilter]);

  const loadInbox = useCallback(async () => {
    setInboxLoading(true);
    try {
      const res = await api.get('/api/follow-ups/inbox');
      setInboxItems(res.data.items ?? []);
    } catch {
      message.error('加载收件箱失败');
    } finally {
      setInboxLoading(false);
    }
  }, []);

  useEffect(() => { loadList(); }, [loadList]);
  useEffect(() => { loadInbox(); }, [loadInbox]);

  // Load customer options
  useEffect(() => {
    api.get('/api/customers', { params: { page: 1, page_size: 100 } })
      .then(res => {
        const opts = (res.data.items ?? []).map((c: { id: number; customer_name: string; customer_code: string }) => ({
          value: c.id,
          label: `${c.customer_code} ${c.customer_name}`,
        }));
        setCustomerOptions(opts);
      })
      .catch(() => {});
  }, []);

  const openComment = (row: FollowUpItem, replyTo?: FollowUpItem) => {
    setCommentTarget(row);
    setCommentReplyTo(replyTo ?? null);
    commentForm.resetFields();
    if (replyTo?.to_sales_user_id) {
      // Reply defaults to send back to original sender (resolved from from_sales_name is name only,
      // so we look up by name among salesUsers)
      const fromUser = salesUsers.find(u => u.name === replyTo.from_sales_name);
      if (fromUser) commentForm.setFieldsValue({ to_sales_user_id: fromUser.id });
    }
    setCommentOpen(true);
  };

  const submitComment = async () => {
    const v = await commentForm.validateFields();
    if (!commentTarget) return;
    setCommentLoading(true);
    try {
      await api.post(`/api/customers/${commentTarget.customer_id}/follow-ups`, {
        kind: 'comment',
        title: commentReplyTo ? `回复: ${commentReplyTo.title}` : '留言',
        content: v.content,
        to_sales_user_id: v.to_sales_user_id ?? null,
        parent_follow_up_id: commentReplyTo?.id ?? null,
      });
      message.success('留言已提交');
      setCommentOpen(false);
      loadList();
      loadInbox();
    } catch {
      // axios interceptor shows error toast
    } finally {
      setCommentLoading(false);
    }
  };

  const openReassign = (row: FollowUpItem) => {
    setReassignTarget(row);
    reassignForm.resetFields();
    setReassignOpen(true);
  };

  const submitReassign = async () => {
    const v = await reassignForm.validateFields();
    if (!reassignTarget) return;
    setReassignLoading(true);
    try {
      await api.patch(`/api/customers/${reassignTarget.customer_id}/assign`, {
        sales_user_id: v.sales_user_id,
        reason: '跟进记录转分配',
      });
      const targetUser = salesUsers.find(u => u.id === v.sales_user_id);
      message.success(`已转给 ${targetUser?.name ?? v.sales_user_id}`);
      setReassignOpen(false);
      loadList();
    } catch {
      // axios interceptor shows error toast
    } finally {
      setReassignLoading(false);
    }
  };

  const salesFilterOptions = [
    { value: -1, label: '全部' },
    ...(mySalesUserId !== undefined ? [{ value: mySalesUserId, label: '我自己' }] : []),
    ...salesUsers
      .filter(u => u.id !== mySalesUserId)
      .map(u => ({ value: u.id, label: u.name })),
  ];

  const actionColumn = {
    title: '操作',
    key: 'action',
    width: 145,
    render: (_: unknown, r: FollowUpItem) => (
      <Space size={4}>
        <Button size="small" icon={<MessageOutlined />} onClick={() => openComment(r)}>
          留言
        </Button>
        {canReassign && (
          <Button size="small" icon={<SwapOutlined />} onClick={() => openReassign(r)}>
            转分配
          </Button>
        )}
      </Space>
    ),
  };

  const listColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 155,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '客户',
      key: 'customer',
      render: (_: unknown, r: FollowUpItem) => (
        <Link to={`/customers?keyword=${encodeURIComponent(r.customer_code)}`}>
          {r.customer_name}
        </Link>
      ),
    },
    {
      title: '类型',
      dataIndex: 'follow_type',
      width: 90,
      render: (t: string) => <Tag color={TYPE_COLOR[t] ?? 'default'}>{t}</Tag>,
    },
    {
      title: '标题',
      dataIndex: 'title',
      ellipsis: true,
    },
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
      render: (v: string | null, r: FollowUpItem) => {
        const text = v ?? '-';
        const indent = !!r.parent_follow_up_id;
        return indent ? <span style={{ paddingLeft: 16, borderLeft: '3px solid #1677ff20' }}>{text}</span> : text;
      },
    },
    {
      title: '下一步时间',
      dataIndex: 'next_action_date',
      width: 120,
      render: (v: string | null) => v ? new Date(v).toLocaleDateString('zh-CN') : '-',
    },
    actionColumn,
  ];

  const inboxColumns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 155,
      render: (t: string) => t ? new Date(t).toLocaleString('zh-CN') : '-',
    },
    {
      title: '发件人 → 收件人 · 客户',
      key: 'meta',
      render: (_: unknown, r: FollowUpItem) => (
        <Space direction="vertical" size={0}>
          <Text>
            <Text strong>{r.from_sales_name ?? r.operator_casdoor_id ?? '—'}</Text>
            {' → '}
            <Text strong>{r.to_sales_name ?? '—'}</Text>
            {' · '}
            <Link to={`/customers?keyword=${encodeURIComponent(r.customer_code)}`}>
              {r.customer_name}
            </Link>
          </Text>
          {r.parent_follow_up_id && (
            <Tag color="blue" style={{ marginTop: 2 }}>回复</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '内容',
      dataIndex: 'content',
      ellipsis: true,
      render: (v: string | null) => v ?? '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: unknown, r: FollowUpItem) => (
        <Button size="small" icon={<MessageOutlined />} onClick={() => openComment(r, r)}>
          回复
        </Button>
      ),
    },
  ];

  const listTab = (
    <>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'flex-end' }} wrap>
        <Select
          value={days}
          onChange={v => { setDays(v); setPage(1); }}
          options={DAYS_OPTIONS}
          style={{ width: 120 }}
        />
        <Select
          value={salesUserFilter === null ? -1 : (salesUserFilter ?? -1)}
          onChange={v => { setSalesUserFilter(v === -1 ? null : v); setPage(1); }}
          options={salesFilterOptions}
          style={{ width: 130 }}
          disabled={salesOnly && mySalesUserId !== undefined}
        />
        <Select
          allowClear
          showSearch
          placeholder="按客户筛选"
          value={customerId}
          onChange={v => { setCustomerId(v); setPage(1); }}
          options={customerOptions}
          filterOption={(input, opt) =>
            (opt?.label as string ?? '').toLowerCase().includes(input.toLowerCase())
          }
          style={{ width: 190 }}
        />
        <Button icon={<ReloadOutlined />} onClick={loadList}>刷新</Button>
      </Space>
      <Table
        rowKey="id"
        loading={loading}
        dataSource={items}
        columns={listColumns}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
        size="middle"
      />
    </>
  );

  const inboxTab = (
    <>
      <Space style={{ marginBottom: 16, justifyContent: 'flex-end', width: '100%' }}>
        <Button icon={<ReloadOutlined />} onClick={loadInbox}>刷新</Button>
      </Space>
      <Table
        rowKey="id"
        loading={inboxLoading}
        dataSource={inboxItems}
        columns={inboxColumns}
        pagination={{ showSizeChanger: true, showTotal: (t) => `共 ${t} 条` }}
        size="middle"
      />
    </>
  );

  return (
    <div className="page-fade">
      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }} wrap>
          <Title level={4} style={{ margin: 0 }}>客户跟进记录</Title>
        </Space>
        <Tabs
          activeKey={activeTab}
          onChange={k => setActiveTab(k as 'list' | 'inbox')}
          items={[
            {
              key: 'list',
              label: '我的跟进记录',
              children: listTab,
            },
            {
              key: 'inbox',
              label: (
                <Badge count={inboxItems.length} offset={[6, 0]} size="small">
                  <span style={{ paddingRight: 8 }}>
                    <InboxOutlined style={{ marginRight: 4 }} />收件箱
                  </span>
                </Badge>
              ),
              children: inboxTab,
            },
          ]}
        />
      </Card>

      {/* 留言 / 回复 Modal */}
      <Modal
        title={commentReplyTo
          ? `回复 ${commentReplyTo.from_sales_name ?? ''} — ${commentTarget?.customer_name ?? ''}`
          : `💬 留言 — ${commentTarget?.customer_name ?? ''}`}
        open={commentOpen}
        onOk={submitComment}
        onCancel={() => setCommentOpen(false)}
        okText="提交"
        cancelText="取消"
        confirmLoading={commentLoading}
        destroyOnClose
      >
        <Form form={commentForm} layout="vertical">
          {!commentReplyTo && (
            <Form.Item name="to_sales_user_id" label="定向发给（可选）">
              <Select
                allowClear
                showSearch
                optionFilterProp="label"
                placeholder="留空=普通跟进，选择=定向留言给某销售"
                options={salesUsers.map(u => ({ value: u.id, label: u.name }))}
              />
            </Form.Item>
          )}
          {commentReplyTo && (
            <Form.Item name="to_sales_user_id" label="回复给">
              <Select
                showSearch
                optionFilterProp="label"
                options={salesUsers.map(u => ({ value: u.id, label: u.name }))}
              />
            </Form.Item>
          )}
          <Form.Item
            name="content"
            label="内容"
            rules={[{ required: true, message: '请填写内容' }]}
          >
            <TextArea rows={4} placeholder="请输入跟进留言内容…" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 转分配 Modal */}
      <Modal
        title={`🔁 转分配 — ${reassignTarget?.customer_name ?? ''}`}
        open={reassignOpen}
        onOk={submitReassign}
        onCancel={() => setReassignOpen(false)}
        okText="确认转分配"
        cancelText="取消"
        confirmLoading={reassignLoading}
        destroyOnClose
      >
        <Form form={reassignForm} layout="vertical">
          <Form.Item
            name="sales_user_id"
            label="转给销售"
            rules={[{ required: true, message: '请选择销售' }]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              placeholder="请选择要转给的销售"
              options={salesUsers.map(u => ({ value: u.id, label: u.name }))}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

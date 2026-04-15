import { useEffect, useState } from 'react';
import {
  Button, Card, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography,
  Popconfirm, Switch, InputNumber, message as antdMessage, Alert,
} from 'antd';
import {
  PlusOutlined, ThunderboltOutlined, UserOutlined, ApartmentOutlined,
  EditOutlined, DeleteOutlined, ReloadOutlined, ClockCircleOutlined,
  RetweetOutlined, CloudDownloadOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';

const { Title, Text, Paragraph } = Typography;

interface SalesUser {
  id: number;
  name: string;
  email?: string | null;
  phone?: string | null;
  regions?: string[] | null;
  industries?: string[] | null;
  max_customers?: number | null;
  is_active: boolean;
  note?: string | null;
  created_at: string;
}

interface Rule {
  id: number;
  name: string;
  industry?: string | null;
  region?: string | null;
  customer_level?: string | null;
  sales_user_id?: number | null;
  sales_user_ids?: number[] | null;
  cursor?: number;
  priority: number;
  is_active: boolean;
  created_at: string;
}

interface RecycleItem {
  customer_id: number;
  customer_code: string;
  from_user_id: number | null;
  last_follow_time: string | null;
  reason: string;
}

interface AutoAssignItem {
  customer_id: number;
  customer_code: string;
  matched_rule_id: number | null;
  sales_user_id: number | null;
  reason: string;
}

export default function SalesTeam() {
  const [users, setUsers] = useState<SalesUser[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [loading, setLoading] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [userEditing, setUserEditing] = useState<SalesUser | null>(null);
  const [userForm] = Form.useForm<SalesUser & { regions?: string[] | string; industries?: string[] | string }>();
  const [ruleOpen, setRuleOpen] = useState(false);
  const [ruleEditing, setRuleEditing] = useState<Rule | null>(null);
  const [ruleForm] = Form.useForm<any>();
  const [autoResult, setAutoResult] = useState<{ total_scanned: number; total_assigned: number; items: AutoAssignItem[]; dry_run: boolean } | null>(null);
  const [autoLoading, setAutoLoading] = useState(false);
  const [staleDays, setStaleDays] = useState(30);
  const [recycleResult, setRecycleResult] = useState<{ total_scanned: number; total_recycled: number; stale_days: number; dry_run: boolean; items: RecycleItem[] } | null>(null);
  const [recycleLoading, setRecycleLoading] = useState(false);
  const [ruleMode, setRuleMode] = useState<'single' | 'roundrobin'>('single');
  const [casdoorLoading, setCasdoorLoading] = useState(false);
  const [casdoorResult, setCasdoorResult] = useState<any>(null);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [u, r] = await Promise.all([
        api.get<SalesUser[]>('/api/sales/users', { params: { active_only: false } }),
        api.get<Rule[]>('/api/sales/rules', { params: { active_only: false } }),
      ]);
      setUsers(u.data);
      setRules(r.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  const openNewUser = () => {
    setUserEditing(null);
    userForm.resetFields();
    userForm.setFieldsValue({ is_active: true } as any);
    setUserOpen(true);
  };

  const openEditUser = (u: SalesUser) => {
    setUserEditing(u);
    userForm.setFieldsValue({
      ...u,
      regions: u.regions?.join(',') as any,
      industries: u.industries?.join(',') as any,
    });
    setUserOpen(true);
  };

  const submitUser = async () => {
    const v = await userForm.validateFields();
    const body = {
      ...v,
      regions: typeof v.regions === 'string' ? v.regions.split(',').map((s) => s.trim()).filter(Boolean) : v.regions,
      industries: typeof v.industries === 'string' ? v.industries.split(',').map((s) => s.trim()).filter(Boolean) : v.industries,
    };
    if (userEditing) await api.patch(`/api/sales/users/${userEditing.id}`, body);
    else await api.post('/api/sales/users', body);
    antdMessage.success(userEditing ? '已更新' : '已创建');
    setUserOpen(false);
    loadAll();
  };

  const deactivateUser = async (u: SalesUser) => {
    await api.delete(`/api/sales/users/${u.id}`);
    antdMessage.success('已停用');
    loadAll();
  };

  const openNewRule = () => {
    setRuleEditing(null);
    ruleForm.resetFields();
    ruleForm.setFieldsValue({ priority: 100, is_active: true } as any);
    setRuleOpen(true);
  };

  const openEditRule = (r: Rule) => {
    setRuleEditing(r);
    ruleForm.setFieldsValue(r);
    setRuleMode(r.sales_user_ids && r.sales_user_ids.length > 0 ? 'roundrobin' : 'single');
    setRuleOpen(true);
  };

  const submitRule = async () => {
    const v = await ruleForm.validateFields();
    // Clear the non-selected target mode to avoid mixed state
    const body: any = { ...v };
    if (ruleMode === 'single') {
      body.sales_user_ids = null;
    } else {
      body.sales_user_id = null;
    }
    if (ruleEditing) await api.patch(`/api/sales/rules/${ruleEditing.id}`, body);
    else await api.post('/api/sales/rules', body);
    antdMessage.success(ruleEditing ? '已更新' : '已创建');
    setRuleOpen(false);
    loadAll();
  };

  const deleteRule = async (r: Rule) => {
    await api.delete(`/api/sales/rules/${r.id}`);
    antdMessage.success('已删除');
    loadAll();
  };

  const runAuto = async (dry: boolean) => {
    setAutoLoading(true);
    try {
      const { data } = await api.post('/api/sales/auto-assign', { dry_run: dry, only_unassigned: true });
      setAutoResult(data);
      if (!dry && data.total_assigned > 0) antdMessage.success(`已分配 ${data.total_assigned} 个客户`);
      else if (!dry) antdMessage.info('没有可分配的客户');
    } finally {
      setAutoLoading(false);
    }
  };

  const syncFromCasdoor = async (dry: boolean) => {
    setCasdoorLoading(true);
    try {
      const { data } = await api.post('/api/sales/users/sync-from-casdoor', { dry_run: dry });
      setCasdoorResult(data);
      if (!dry) {
        antdMessage.success(
          `同步完成: 新增 ${data.created} · 更新 ${data.updated} · 不变 ${data.unchanged} · 跳过 ${data.skipped}`
        );
        loadAll();
      }
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '同步失败');
    } finally {
      setCasdoorLoading(false);
    }
  };

  const runRecycle = async (dry: boolean) => {
    setRecycleLoading(true);
    try {
      const { data } = await api.post('/api/sales/auto-recycle', { stale_days: staleDays, dry_run: dry });
      setRecycleResult(data);
      if (!dry && data.total_recycled > 0) antdMessage.success(`已回收 ${data.total_recycled} 个客户到商机池`);
      else if (!dry) antdMessage.info(`扫描 ${data.total_scanned} 个, 无客户超过 ${staleDays} 天未跟进`);
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '过期回收失败');
    } finally {
      setRecycleLoading(false);
    }
  };

  const userById = (id?: number | null) => users.find((u) => u.id === id);

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 12, marginBottom: 16,
          background: 'linear-gradient(120deg, #6366f1 0%, #ec4899 100%)',
          color: 'white',
        }}
        styles={{ body: { padding: 24 } }}
      >
        <Space direction="vertical" size={4}>
          <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>SALES · 销售团队</Text>
          <Title level={2} style={{ color: 'white', margin: 0 }}>
            <UserOutlined /> 销售成员 · 分配规则 · 自动分配
          </Title>
          <Paragraph style={{ color: 'rgba(255,255,255,0.85)', marginBottom: 0 }}>
            维护销售人员档案 + 分配规则（行业 / 地区 / 客户级别），对未分配客户一键自动分配
          </Paragraph>
        </Space>
      </Card>

      <Tabs
        items={[
          {
            key: 'users',
            label: <Space><UserOutlined />销售成员 <Tag>{users.length}</Tag></Space>,
            children: (
              <Card
                bordered={false}
                extra={<Space>
                  <Button icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button>
                  <Button icon={<CloudDownloadOutlined />} loading={casdoorLoading}
                          onClick={() => syncFromCasdoor(true)}>
                    Casdoor 干跑
                  </Button>
                  <Button type="primary" icon={<CloudDownloadOutlined />} loading={casdoorLoading}
                          onClick={() => syncFromCasdoor(false)}>
                    从 Casdoor 同步
                  </Button>
                  <Button icon={<PlusOutlined />} onClick={openNewUser}>手动新增 (应急)</Button>
                </Space>}
              >
                {casdoorResult && (
                  <Alert
                    type={casdoorResult.dry_run ? 'info' : 'success'} closable
                    style={{ marginBottom: 12 }}
                    message={`Casdoor 同步 (${casdoorResult.dry_run ? 'dry-run' : '已落库'}): 抓取 ${casdoorResult.total_fetched} 人 | 新增 ${casdoorResult.created} · 更新 ${casdoorResult.updated} · 不变 ${casdoorResult.unchanged} · 跳过 ${casdoorResult.skipped}`}
                  />
                )}
                <Alert
                  type="warning" showIcon style={{ marginBottom: 12 }}
                  message="建议: 不要手动建销售, 用 '从 Casdoor 同步' 拉统一认证里的用户, 这样 casdoor_user_id 能对得上, 登录/退出会自动联动."
                />
                <Table<SalesUser>
                  rowKey="id" loading={loading} dataSource={users} pagination={{ pageSize: 20 }}
                  columns={[
                    { title: 'ID', dataIndex: 'id', width: 60 },
                    { title: '姓名', dataIndex: 'name', render: (v, r) => (
                      <Space><Text strong>{v}</Text>{!r.is_active && <Tag>已停用</Tag>}</Space>
                    )},
                    { title: '邮箱', dataIndex: 'email' },
                    { title: '电话', dataIndex: 'phone' },
                    { title: '区域', dataIndex: 'regions', render: (v: string[] | null) => (v || []).map((x) => <Tag key={x} color="blue">{x}</Tag>) },
                    { title: '行业', dataIndex: 'industries', render: (v: string[] | null) => (v || []).map((x) => <Tag key={x} color="purple">{x}</Tag>) },
                    { title: '容量', dataIndex: 'max_customers', width: 80,
                      render: (v: number | null) => v ? <Tag color="orange">{v} 上限</Tag> : <Tag>不限</Tag> },
                    { title: '备注', dataIndex: 'note', ellipsis: true },
                    { title: '操作', width: 160, render: (_, r) => (
                      <Space>
                        <Button size="small" icon={<EditOutlined />} onClick={() => openEditUser(r)}>编辑</Button>
                        {r.is_active && (
                          <Popconfirm title="停用该销售？" onConfirm={() => deactivateUser(r)}>
                            <Button size="small" danger icon={<DeleteOutlined />}>停用</Button>
                          </Popconfirm>
                        )}
                      </Space>
                    )},
                  ]}
                />
              </Card>
            ),
          },
          {
            key: 'rules',
            label: <Space><ApartmentOutlined />分配规则 <Tag>{rules.length}</Tag></Space>,
            children: (
              <Card
                bordered={false}
                extra={<Space>
                  <Button icon={<ReloadOutlined />} onClick={loadAll}>刷新</Button>
                  <Button type="primary" icon={<PlusOutlined />} onClick={openNewRule}>新增规则</Button>
                </Space>}
              >
                <Alert
                  showIcon style={{ marginBottom: 12 }} type="info"
                  message="规则按 priority 升序匹配，字段为空=不限。所有字段都空=兜底规则（priority 设大）。"
                />
                <Table<Rule>
                  rowKey="id" loading={loading} dataSource={rules} pagination={{ pageSize: 20 }}
                  columns={[
                    { title: 'ID', dataIndex: 'id', width: 60 },
                    { title: '名称', dataIndex: 'name', render: (v, r) => (
                      <Space><Text strong>{v}</Text>{!r.is_active && <Tag>已禁用</Tag>}</Space>
                    )},
                    { title: '优先级', dataIndex: 'priority', width: 90, sorter: (a, b) => a.priority - b.priority },
                    { title: '行业', dataIndex: 'industry', render: (v) => v || <Text type="secondary">不限</Text> },
                    { title: '地区', dataIndex: 'region', render: (v) => v || <Text type="secondary">不限</Text> },
                    { title: '级别', dataIndex: 'customer_level', render: (v) => v || <Text type="secondary">不限</Text> },
                    { title: '分配给', render: (_: any, r: Rule) => {
                      if (r.sales_user_ids && r.sales_user_ids.length > 0) {
                        return (
                          <Space wrap size={4}>
                            <Tag icon={<RetweetOutlined />} color="green">轮询 · cursor {r.cursor}</Tag>
                            {r.sales_user_ids.map((uid) => {
                              const u = userById(uid);
                              return <Tag key={uid} color="geekblue">{u ? u.name : `#${uid}`}</Tag>;
                            })}
                          </Space>
                        );
                      }
                      const u = userById(r.sales_user_id);
                      return u ? <Tag color="geekblue">{u.name}</Tag> : <Tag>未设</Tag>;
                    }},
                    { title: '操作', width: 160, render: (_, r) => (
                      <Space>
                        <Button size="small" icon={<EditOutlined />} onClick={() => openEditRule(r)}>编辑</Button>
                        <Popconfirm title="删除该规则？" onConfirm={() => deleteRule(r)}>
                          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                        </Popconfirm>
                      </Space>
                    )},
                  ]}
                />
              </Card>
            ),
          },
          {
            key: 'recycle',
            label: <Space><ClockCircleOutlined />过期回收</Space>,
            children: (
              <Card bordered={false}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Alert
                    type="info" showIcon
                    message="把超过 N 天没跟进的客户退回商机池 (sales_user_id 置 null)。last_follow_time 为空也视作超期。"
                  />
                  <Space>
                    <Text>阈值</Text>
                    <InputNumber min={1} max={365} value={staleDays} onChange={(v) => setStaleDays(v || 30)} />
                    <Text>天</Text>
                    <Button icon={<ClockCircleOutlined />} loading={recycleLoading} onClick={() => runRecycle(true)}>
                      干跑（预览）
                    </Button>
                    <Button type="primary" danger icon={<ClockCircleOutlined />} loading={recycleLoading} onClick={() => runRecycle(false)}>
                      执行回收
                    </Button>
                  </Space>
                  {recycleResult && (
                    <Card size="small" title={
                      <Space>
                        <Text>结果</Text>
                        {recycleResult.dry_run && <Tag color="gold">dry-run</Tag>}
                        <Tag>阈值 {recycleResult.stale_days} 天</Tag>
                        <Tag color="orange">扫描 {recycleResult.total_scanned}</Tag>
                        <Tag color="red">回收 {recycleResult.total_recycled}</Tag>
                      </Space>
                    }>
                      <Table<RecycleItem>
                        rowKey="customer_id" dataSource={recycleResult.items} size="small" pagination={{ pageSize: 20 }}
                        columns={[
                          { title: '客户编号', dataIndex: 'customer_code', width: 160 },
                          { title: '原负责销售', dataIndex: 'from_user_id', render: (v: number | null) => {
                            const u = userById(v); return u ? <Tag>{u.name}</Tag> : <Tag>#{v}</Tag>;
                          }},
                          { title: '最近跟进', dataIndex: 'last_follow_time', render: (v: string | null) => v ? new Date(v).toLocaleDateString() : '从未' },
                          { title: '原因', dataIndex: 'reason' },
                        ]}
                      />
                    </Card>
                  )}
                </Space>
              </Card>
            ),
          },
          {
            key: 'auto',
            label: <Space><ThunderboltOutlined />自动分配</Space>,
            children: (
              <Card bordered={false}>
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <Alert
                    type="warning" showIcon
                    message="对所有 sales_user_id 为空的客户跑一遍规则。dry-run 只预览不写库。"
                  />
                  <Space>
                    <Button icon={<ThunderboltOutlined />} loading={autoLoading} onClick={() => runAuto(true)}>
                      干跑（预览）
                    </Button>
                    <Button type="primary" icon={<ThunderboltOutlined />} loading={autoLoading} onClick={() => runAuto(false)}>
                      执行自动分配
                    </Button>
                  </Space>
                  {autoResult && (
                    <Card size="small" title={
                      <Space>
                        <Text>结果</Text>
                        {autoResult.dry_run && <Tag color="gold">dry-run</Tag>}
                        <Tag>扫描 {autoResult.total_scanned}</Tag>
                        <Tag color="green">分配 {autoResult.total_assigned}</Tag>
                      </Space>
                    }>
                      <Table<AutoAssignItem>
                        rowKey="customer_id" dataSource={autoResult.items} size="small" pagination={{ pageSize: 20 }}
                        columns={[
                          { title: '客户编号', dataIndex: 'customer_code', width: 160 },
                          { title: '分配给', dataIndex: 'sales_user_id', render: (v: number | null) => {
                            const u = userById(v); return u ? <Tag color="geekblue">{u.name}</Tag> : <Tag>未匹配</Tag>;
                          }},
                          { title: '命中规则', dataIndex: 'matched_rule_id' },
                          { title: '原因', dataIndex: 'reason' },
                        ]}
                      />
                    </Card>
                  )}
                </Space>
              </Card>
            ),
          },
        ]}
      />

      {/* user modal */}
      <Modal
        title={userEditing ? '编辑销售' : '新增销售'}
        open={userOpen} onOk={submitUser} onCancel={() => setUserOpen(false)} destroyOnClose
      >
        <Form form={userForm} layout="vertical" preserve={false}>
          <Form.Item name="name" label="姓名" rules={[{ required: true }]}>
            <Input placeholder="张三" />
          </Form.Item>
          <Form.Item name="email" label="邮箱"><Input /></Form.Item>
          <Form.Item name="phone" label="电话"><Input /></Form.Item>
          <Form.Item name="regions" label="负责区域" tooltip="用英文逗号分隔, 如 华东,华北">
            <Input placeholder="华东,华北" />
          </Form.Item>
          <Form.Item name="industries" label="擅长行业" tooltip="用英文逗号分隔">
            <Input placeholder="能源,AI" />
          </Form.Item>
          <Form.Item name="max_customers" label="容量上限" tooltip="同时承接客户数, 留空=不限制">
            <InputNumber min={1} max={9999} style={{ width: 160 }} placeholder="空=无限" />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item name="note" label="备注"><Input.TextArea rows={2} /></Form.Item>
        </Form>
      </Modal>

      {/* rule modal */}
      <Modal
        title={ruleEditing ? '编辑规则' : '新增分配规则'}
        open={ruleOpen} onOk={submitRule} onCancel={() => setRuleOpen(false)} destroyOnClose
      >
        <Form form={ruleForm} layout="vertical" preserve={false}>
          <Form.Item name="name" label="规则名称" rules={[{ required: true }]}>
            <Input placeholder="华东能源" />
          </Form.Item>
          <Form.Item name="industry" label="匹配行业" tooltip="空=不限">
            <Input placeholder="能源" />
          </Form.Item>
          <Form.Item name="region" label="匹配地区" tooltip="空=不限">
            <Input placeholder="华东" />
          </Form.Item>
          <Form.Item name="customer_level" label="匹配客户级别" tooltip="空=不限">
            <Input placeholder="KEY / NORMAL" />
          </Form.Item>
          <Form.Item label="分配模式">
            <Select
              value={ruleMode} onChange={(v) => setRuleMode(v)} style={{ width: 200 }}
              options={[
                { value: 'single', label: '单人 — 固定分给一个销售' },
                { value: 'roundrobin', label: '轮询 — 多个销售轮流' },
              ]}
            />
          </Form.Item>
          {ruleMode === 'single' ? (
            <Form.Item name="sales_user_id" label="分配给" rules={[{ required: true }]}>
              <Select
                showSearch optionFilterProp="label"
                options={users.filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.name }))}
              />
            </Form.Item>
          ) : (
            <Form.Item name="sales_user_ids" label="轮询候选 (至少选 1 个, 命中此规则的客户会按顺序轮流派给列表中的销售)"
              rules={[{ required: true, type: 'array', min: 1, message: '至少选 1 个销售' }]}>
              <Select
                mode="multiple" showSearch optionFilterProp="label"
                placeholder="选择候选销售, 按选择顺序轮流"
                options={users.filter((u) => u.is_active).map((u) => ({ value: u.id, label: u.name }))}
              />
            </Form.Item>
          )}
          <Form.Item name="priority" label="优先级" tooltip="越小越先命中，默认 100"
            rules={[{ required: true }]}>
            <InputNumber min={0} max={9999} style={{ width: 160 }} />
          </Form.Item>
          <Form.Item name="is_active" label="启用" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}

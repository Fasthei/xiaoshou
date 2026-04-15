import { useEffect, useState } from 'react';
import {
  Button, Card, Input, List, Space, Tag, Typography, Empty, Modal, Form, message,
  Select, Alert,
} from 'antd';
import {
  SearchOutlined, BulbFilled, RocketOutlined, LinkOutlined,
  UserSwitchOutlined, ThunderboltOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';

interface SalesUserLite { id: number; name: string; email?: string | null; is_active: boolean }

const { Title, Text, Paragraph } = Typography;

interface Lead {
  title: string;
  url: string;
  description: string;
  inferred_industry?: string | null;
}

const HOT_KEYWORDS = [
  '新能源 储能 上海', 'AI 大模型 初创 北京', '跨境电商 SaaS', '智能制造 工业互联网',
  'Fintech 支付', '医疗 AI', '云安全 零信任', '智慧城市 政务',
];

export default function Leads() {
  const [q, setQ] = useState('');
  const [loading, setLoading] = useState(false);
  const [leads, setLeads] = useState<Lead[]>([]);
  const [openPromote, setOpenPromote] = useState(false);
  const [picking, setPicking] = useState<Lead | null>(null);
  const [form] = Form.useForm<{ customer_code: string; customer_name: string; industry?: string; sales_user_id?: number | null }>();
  const [salesUsers, setSalesUsers] = useState<SalesUserLite[]>([]);
  const [autoLoading, setAutoLoading] = useState(false);

  useEffect(() => {
    api.get<SalesUserLite[]>('/api/sales/users').then((r) => setSalesUsers(r.data)).catch(() => setSalesUsers([]));
  }, []);

  const doSearch = async (kw?: string) => {
    const query = (kw ?? q).trim();
    if (!query) return;
    setQ(query);
    setLoading(true);
    try {
      const { data } = await api.get<Lead[]>('/api/enrich/leads', { params: { q: query, num: 10 } });
      setLeads(data);
    } finally {
      setLoading(false);
    }
  };

  const openPromoteFor = (l: Lead) => {
    setPicking(l);
    const code = 'LEAD-' + Math.random().toString(36).slice(2, 10).toUpperCase();
    form.setFieldsValue({ customer_code: code, customer_name: l.title, industry: l.inferred_industry || undefined });
    setOpenPromote(true);
  };

  const promote = async () => {
    const v = await form.validateFields();
    const { sales_user_id, ...body } = v;
    const { data } = await api.post('/api/enrich/leads/promote', {
      ...body,
      source_url: picking?.url,
    });
    if (sales_user_id && data?.id) {
      try {
        await api.patch(`/api/customers/${data.id}/assign`, {
          sales_user_id,
          reason: `Leads 转入时分配 (来源: ${picking?.url || '—'})`,
        });
      } catch (e) {
        message.warning('客户已创建，但分配销售失败（可在客户详情页重试）');
      }
    }
    message.success(`已添加 ${v.customer_name} 为潜在客户${sales_user_id ? ' 并分配销售' : ''}`);
    setOpenPromote(false);
  };

  const runAutoAssign = async () => {
    setAutoLoading(true);
    try {
      const { data } = await api.post('/api/sales/auto-assign', { dry_run: false, only_unassigned: true });
      if (data.total_assigned > 0) {
        message.success(`自动分配完成：扫描 ${data.total_scanned} 个未分配客户，成功分配 ${data.total_assigned} 个`);
      } else {
        message.info(`扫描 ${data.total_scanned} 个未分配客户，没有命中任何规则 — 请先去 销售团队 页建规则`);
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '自动分配失败');
    } finally {
      setAutoLoading(false);
    }
  };

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 12,
          background: 'linear-gradient(120deg, #0ea5e9 0%, #4f46e5 60%, #ec4899 100%)',
          color: 'white',
          marginBottom: 16,
        }}
        styles={{ body: { padding: 28 } }}
      >
        <Space direction="vertical" size={4}>
          <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>
            LEADS · 商机挖掘
          </Text>
          <Title level={2} style={{ color: 'white', margin: 0 }}>
            <BulbFilled /> 搜索潜在客户
          </Title>
          <Paragraph style={{ color: 'rgba(255,255,255,0.85)', marginBottom: 12 }}>
            用关键词（行业 / 地区 / 技术方向）搜公开网页，自动猜行业 → 一键转为客户 → 按规则自动派销售
          </Paragraph>
        </Space>
        <div style={{ marginTop: 8 }}>
          <Button
            ghost icon={<ThunderboltOutlined />} loading={autoLoading}
            style={{ color: 'white', borderColor: 'rgba(255,255,255,0.6)' }}
            onClick={runAutoAssign}
          >
            对所有未分配客户跑一次规则自动分配
          </Button>
        </div>
        <Space.Compact style={{ width: '100%', maxWidth: 560 }}>
          <Input
            size="large"
            placeholder="例如：新能源 储能 上海"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onPressEnter={() => doSearch()}
            prefix={<SearchOutlined />}
          />
          <Button type="primary" size="large" loading={loading} onClick={() => doSearch()}>
            搜索
          </Button>
        </Space.Compact>
        <div style={{ marginTop: 12 }}>
          <Space wrap>
            {HOT_KEYWORDS.map((k) => (
              <Tag
                key={k}
                style={{ cursor: 'pointer', background: 'rgba(255,255,255,0.18)', borderColor: 'transparent', color: 'white' }}
                onClick={() => doSearch(k)}
              >
                {k}
              </Tag>
            ))}
          </Space>
        </div>
      </Card>

      <Card bordered={false} style={{ borderRadius: 12 }}>
        {!loading && leads.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="输入关键词开始搜索" />
        ) : (
          <List
            loading={loading}
            dataSource={leads}
            renderItem={(l) => (
              <List.Item
                actions={[
                  <Button
                    key="open"
                    icon={<LinkOutlined />}
                    href={l.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    打开
                  </Button>,
                  <Button
                    key="promote"
                    type="primary"
                    icon={<RocketOutlined />}
                    onClick={() => openPromoteFor(l)}
                  >
                    转为客户
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={
                    <Space wrap>
                      <Text strong>{l.title}</Text>
                      {l.inferred_industry ? <Tag color="purple">{l.inferred_industry}</Tag> : null}
                    </Space>
                  }
                  description={
                    <Space direction="vertical" size={2}>
                      <Text type="secondary" style={{ fontSize: 12 }} copyable={{ text: l.url }}>
                        {l.url}
                      </Text>
                      <Text>{l.description || '—'}</Text>
                    </Space>
                  }
                />
              </List.Item>
            )}
          />
        )}
      </Card>

      <Modal
        title="转为客户"
        open={openPromote}
        onOk={promote}
        onCancel={() => setOpenPromote(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="customer_code" label="客户编号" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="industry" label="行业">
            <Input placeholder="可选，AI 已猜测填入" />
          </Form.Item>
          <Form.Item name="sales_user_id" label={<Space><UserSwitchOutlined />分配销售 (可选)</Space>}
            tooltip="留空 = 先入商机池，后续用规则自动分配 或 手动在客户详情分配">
            <Select
              allowClear showSearch placeholder="搜索销售"
              optionFilterProp="label"
              options={salesUsers.filter((u) => u.is_active).map((u) => ({
                value: u.id, label: `${u.name}${u.email ? ' · ' + u.email : ''}`,
              }))}
              notFoundContent={
                <Alert type="info" banner showIcon
                  message="销售团队还没人，去 /sales-team 页先建成员"
                />
              }
            />
          </Form.Item>
          {picking ? (
            <Text type="secondary" style={{ fontSize: 12 }}>
              来源：<code>{picking.url}</code>
            </Text>
          ) : null}
        </Form>
      </Modal>
    </div>
  );
}

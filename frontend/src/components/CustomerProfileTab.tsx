import { useEffect, useState } from 'react';
import {
  Card, List, Tag, Timeline, Space, Typography, Progress, Empty,
  Button, Modal, Form, Input, Select, DatePicker,
  message as antdMessage,
} from 'antd';
import {
  HistoryOutlined, PlusOutlined, PhoneOutlined, MailOutlined,
  WechatOutlined, TeamOutlined, FileTextOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import dayjs from 'dayjs';

const { Text, Paragraph } = Typography;

interface FollowUp {
  id: number;
  customer_id: number;
  kind: string;
  title: string;
  content?: string | null;
  outcome?: string | null;
  next_action_at?: string | null;
  operator_casdoor_id?: string | null;
  created_at: string;
}

interface Completeness {
  customer_id: number;
  score: number;
  tier: 'red' | 'yellow' | 'green';
  missing: string[];
  present: string[];
}

const KIND_META: Record<string, { label: string; icon: any; color: string }> = {
  call:    { label: '电话', icon: <PhoneOutlined />,    color: 'blue' },
  meeting: { label: '面访', icon: <TeamOutlined />,     color: 'geekblue' },
  email:   { label: '邮件', icon: <MailOutlined />,     color: 'purple' },
  wechat:  { label: '微信', icon: <WechatOutlined />,   color: 'green' },
  note:    { label: '备注', icon: <FileTextOutlined />, color: 'default' },
  other:   { label: '其他', icon: <FileTextOutlined />, color: 'default' },
};

const OUTCOME_COLOR: Record<string, string> = {
  positive: 'green', neutral: 'default', negative: 'red', needs_followup: 'orange',
};

export default function CustomerProfileTab({ customerId }: { customerId: number }) {
  const [fus, setFus] = useState<FollowUp[]>([]);
  const [completeness, setCompleteness] = useState<Completeness | null>(null);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [form] = Form.useForm<FollowUp>();

  const load = async () => {
    setLoading(true);
    try {
      const [fRes, cRes] = await Promise.allSettled([
        api.get<FollowUp[]>(`/api/customers/${customerId}/follow-ups`),
        api.get<Completeness>(`/api/customers/${customerId}/completeness`),
      ]);
      setFus(fRes.status === 'fulfilled' && Array.isArray(fRes.value.data) ? fRes.value.data : []);
      setCompleteness(cRes.status === 'fulfilled' ? (cRes.value.data ?? null) : null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [customerId]);

  const submit = async () => {
    const v: any = await form.validateFields();
    try {
      await api.post(`/api/customers/${customerId}/follow-ups`, {
        ...v,
        next_action_at: v.next_action_at ? dayjs(v.next_action_at).toISOString() : null,
      });
      antdMessage.success('已记录跟进');
      setOpen(false); form.resetFields();
      load();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '新增跟进失败');
    }
  };

  const del = async (id: number) => {
    try {
      await api.delete(`/api/customers/${customerId}/follow-ups/${id}`);
      load();
    } catch (e: any) {
      antdMessage.error(e?.response?.data?.detail || '删除失败');
    }
  };

  const tierColor = completeness?.tier === 'green' ? '#10b981'
    : completeness?.tier === 'yellow' ? '#f59e0b' : '#ef4444';

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {completeness && (
        <Card size="small" title={<Space>📋 档案完整度</Space>}>
          <Space direction="vertical" size="small" style={{ width: '100%' }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 36, fontWeight: 700, color: tierColor }}>
                {completeness.score}
              </div>
              <Tag color={completeness.tier === 'green' ? 'green' : completeness.tier === 'yellow' ? 'orange' : 'red'}>
                {completeness.tier === 'green' ? '优秀' : completeness.tier === 'yellow' ? '一般' : '急需补全'}
              </Tag>
            </div>
            <Progress percent={completeness.score} strokeColor={tierColor} showInfo={false} />
            <Space wrap size={4} style={{ marginTop: 8 }}>
              {completeness.present.map((f) => (
                <Tag key={f} color="success">{f} ✓</Tag>
              ))}
              {completeness.missing.map((f) => (
                <Tag key={f} color="default">缺: {f}</Tag>
              ))}
            </Space>
          </Space>
        </Card>
      )}

      <Card
        size="small"
        title={<Space><HistoryOutlined />跟进日志 <Tag>{fus.length}</Tag></Space>}
        extra={
          <Button type="primary" size="small" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
            新增跟进
          </Button>
        }
      >
        {loading ? <Text type="secondary">加载中...</Text>
         : fus.length === 0 ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有跟进记录, 点右上 '新增跟进'" />
         : (
          <Timeline
            items={fus.map((fu) => {
              const m = KIND_META[fu.kind] || KIND_META.other;
              return {
                dot: m.icon,
                color: m.color,
                children: (
                  <Space direction="vertical" size={2}>
                    <Space wrap>
                      <Text strong>{fu.title}</Text>
                      <Tag color={m.color}>{m.label}</Tag>
                      {fu.outcome && <Tag color={OUTCOME_COLOR[fu.outcome] || 'default'}>{fu.outcome}</Tag>}
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {new Date(fu.created_at).toLocaleString()}
                      </Text>
                      <Button size="small" type="link" danger onClick={() => del(fu.id)}>删除</Button>
                    </Space>
                    {fu.content && <Paragraph style={{ marginBottom: 0 }}>{fu.content}</Paragraph>}
                    {fu.next_action_at && (
                      <Text type="secondary">下一步: {new Date(fu.next_action_at).toLocaleString()}</Text>
                    )}
                  </Space>
                ),
              };
            })}
          />
        )}
      </Card>

      <Modal title="新增跟进" open={open} onOk={submit} onCancel={() => setOpen(false)} destroyOnClose>
        <Form form={form} layout="vertical" initialValues={{ kind: 'call' }}>
          <Form.Item name="kind" label="类型" rules={[{ required: true }]}>
            <Select
              options={Object.entries(KIND_META).map(([v, m]) => ({ value: v, label: m.label }))}
            />
          </Form.Item>
          <Form.Item name="title" label="标题" rules={[{ required: true }]}>
            <Input placeholder="例: 首次电话沟通 / 产品演示" />
          </Form.Item>
          <Form.Item name="content" label="内容">
            <Input.TextArea rows={4} />
          </Form.Item>
          <Form.Item name="outcome" label="结果">
            <Select
              allowClear
              options={[
                { value: 'positive', label: '积极' },
                { value: 'neutral', label: '中性' },
                { value: 'negative', label: '消极' },
                { value: 'needs_followup', label: '需跟进' },
              ]}
            />
          </Form.Item>
          <Form.Item name="next_action_at" label="下一步时间">
            <DatePicker showTime style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}

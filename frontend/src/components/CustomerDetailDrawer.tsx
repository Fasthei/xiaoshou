import { useEffect, useState } from 'react';
import {
  Drawer, Tabs, Descriptions, Tag, Space, Typography, List, Avatar, Empty,
  Skeleton, Button, Card, Timeline, Select, Input, Modal, Form,
  message as antdMessage,
} from 'antd';
import {
  CloudServerOutlined, SyncOutlined, LinkOutlined, BulbOutlined,
  UserSwitchOutlined, HistoryOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import type { Customer } from '../types';
import HealthRadar from './HealthRadar';
import CustomerInsightPanel from './CustomerInsightPanel';

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
  const [loading, setLoading] = useState(false);
  const [resources, setResources] = useState<CloudCostResource[]>([]);
  const [matchField, setMatchField] = useState('');
  const [health, setHealth] = useState<any>(null);
  const [timeline, setTimeline] = useState<any[]>([]);
  const [salesUsers, setSalesUsers] = useState<any[]>([]);
  const [assignLog, setAssignLog] = useState<any[]>([]);
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignForm] = Form.useForm<{ sales_user_id?: number | null; reason?: string }>();

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
      open={open} onClose={onClose} width={640} destroyOnClose
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
                    <Tag color={customer.customer_status === 'active' ? 'green' : 'default'}>
                      {customer.customer_status}
                    </Tag>
                  </Descriptions.Item>
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
              key: 'insight',
              label: (
                <Space><BulbOutlined style={{ color: '#f59e0b' }} />AI 洞察</Space>
              ),
              children: <CustomerInsightPanel customerId={customer.id} />,
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

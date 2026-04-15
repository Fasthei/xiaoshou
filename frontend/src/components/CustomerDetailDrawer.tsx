import { useEffect, useState } from 'react';
import {
  Drawer, Tabs, Descriptions, Tag, Space, Typography, List, Avatar, Empty,
  Skeleton, Button, Card,
} from 'antd';
import { CloudServerOutlined, SyncOutlined, LinkOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { Customer } from '../types';
import HealthRadar from './HealthRadar';

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

  useEffect(() => {
    if (open && customer) {
      loadResources();
      api.get(`/api/customers/${customer.id}/health`).then(({ data }) => setHealth(data)).catch(() => setHealth(null));
    }
  }, [open, customer?.id]);

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
    </Drawer>
  );
}

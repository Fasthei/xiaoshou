import { useEffect, useState } from 'react';
import {
  Card, Col, Row, Skeleton, Tag, Space, Typography, Button, Empty,
  Table, Progress, Statistic, Alert,
} from 'antd';
import {
  CheckSquareOutlined, AimOutlined, ClockCircleOutlined, FireOutlined,
  RightOutlined, UserOutlined,
} from '@ant-design/icons';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/axios';

const { Title, Text } = Typography;

interface TodoDue {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  last_follow_at: string | null;
  last_follow_title: string | null;
  next_action_at: string | null;
  next_action_hint: string | null;
  overdue: boolean;
}

interface TodoStale {
  customer_id: number;
  customer_code: string;
  customer_name: string;
  last_follow_at: string | null;
  days_since_follow: number | null;
}

interface TodosResp {
  unbound: boolean;
  sales_user_name?: string;
  due: TodoDue[];
  stale: TodoStale[];
}

interface MyKpiResp {
  sales_user_id: number | null;
  sales_user_name: string;
  target_year: number;
  annual_target: number;
  ytd_achievement: number;
  progress_pct: number;
  gap: number;
  month: string;
  month_new_opportunities: number;
  month_follow_ups: number;
  month_deals: number;
  month_signed_amount: number;
  unbound: boolean;
}

interface MyTargetProgressResp {
  sales_user_id: number;
  sales_user_name: string;
  target_year: number | null;
  annual_sales_target: number | null;
  annual_profit_target: number | null;
  profit_margin_target: number | null;
  ytd_sales: number;
  ytd_profit: number;
  sales_progress_pct: number;
  profit_progress_pct: number;
  days_remaining_in_year: number;
  daily_sales_target_to_close: number;
  daily_profit_target_to_close: number;
  unbound: boolean;
}

function fmtMoney(n: number | null | undefined): string {
  if (n == null) return '¥0';
  return '¥' + Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 0 });
}

function fmtRelDays(iso: string | null): string {
  if (!iso) return '从未跟进';
  const d = new Date(iso);
  const diff = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diff < 0) return `${-diff} 天后`;
  if (diff === 0) return '今天';
  if (diff === 1) return '昨天';
  return `${diff} 天前`;
}

function fmtDueDays(iso: string | null): { text: string; overdue: boolean } {
  if (!iso) return { text: '—', overdue: false };
  const d = new Date(iso);
  const diff = Math.floor((d.getTime() - Date.now()) / 86400000);
  if (diff < 0) return { text: `逾期 ${-diff} 天`, overdue: true };
  if (diff === 0) return { text: '今天到期', overdue: true };
  if (diff === 1) return { text: '明天到期', overdue: false };
  return { text: `${diff} 天后`, overdue: false };
}

export default function SalesHome() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [todos, setTodos] = useState<TodosResp | null>(null);
  const [kpi, setKpi] = useState<MyKpiResp | null>(null);
  const [targetProgress, setTargetProgress] = useState<MyTargetProgressResp | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const [t, k, tp] = await Promise.allSettled([
        api.get<TodosResp>('/api/metrics/my-todos?stale_days=14&upcoming_days=7'),
        api.get<MyKpiResp>('/api/metrics/my-kpi'),
        api.get<MyTargetProgressResp>('/api/sales/me/target-progress'),
      ]);
      if (t.status === 'fulfilled') setTodos(t.value.data);
      if (k.status === 'fulfilled') setKpi(k.value.data);
      if (tp.status === 'fulfilled') setTargetProgress(tp.value.data);
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const goFollow = (customerId: number) => {
    navigate(`/customers?open=${customerId}`);
  };

  const dueCount = todos?.due?.length ?? 0;
  const staleCount = todos?.stale?.length ?? 0;

  return (
    <div className="page-fade">
      <div style={{ marginBottom: 20 }}>
        <Title level={3} style={{ margin: 0 }}>
          <Space><UserOutlined />销售工作台</Space>
        </Title>
        <Text type="secondary">
          {kpi?.sales_user_name ? `${kpi.sales_user_name} · ` : ''}聚焦跟进 + 目标达成
        </Text>
      </div>

      {kpi?.unbound && (
        <Alert
          type="warning" showIcon style={{ marginBottom: 16 }}
          message="当前登录账号未绑定本地销售档案"
          description="请联系管理员在'销售团队'页把你的 Casdoor 账号同步进来, 否则无法看到个人 KPI / 代办。"
        />
      )}

      {/* 1. 我的代办 */}
      <Card
        title={
          <Space>
            <CheckSquareOutlined style={{ color: '#C19C00' }} />
            <span>我的代办 / 跟进</span>
            {dueCount > 0 && <Tag color="orange">{dueCount} 条到期</Tag>}
            {staleCount > 0 && <Tag color="red">{staleCount} 条冷落</Tag>}
          </Space>
        }
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
        extra={<Link to="/customers"><Button type="link" size="small">去客户管理 <RightOutlined /></Button></Link>}
      >
        {loading ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : dueCount === 0 && staleCount === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" size={4}>
                <Text>暂无到期 / 冷落客户，去跟进更多客户吧 🎉</Text>
                <Link to="/customers"><Button size="small" type="primary">客户管理</Button></Link>
              </Space>
            }
          />
        ) : (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            {dueCount > 0 && (
              <div>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                  <ClockCircleOutlined /> 近期需回访 ({dueCount})
                </Text>
                <Table<TodoDue>
                  rowKey="customer_id"
                  size="small"
                  pagination={false}
                  dataSource={todos?.due ?? []}
                  columns={[
                    {
                      title: '客户', dataIndex: 'customer_name', key: 'name',
                      render: (name, r) => (
                        <Space direction="vertical" size={0}>
                          <Text strong>{name}</Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>{r.customer_code}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: '上次跟进', dataIndex: 'last_follow_at', key: 'last',
                      render: (v, r) => (
                        <Space direction="vertical" size={0}>
                          <Text>{fmtRelDays(v)}</Text>
                          {r.last_follow_title && (
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {r.last_follow_title.length > 24 ? r.last_follow_title.slice(0, 24) + '…' : r.last_follow_title}
                            </Text>
                          )}
                        </Space>
                      ),
                    },
                    {
                      title: '下一步', dataIndex: 'next_action_hint', key: 'hint',
                      render: (v) => v ? (v.length > 30 ? v.slice(0, 30) + '…' : v) : <Text type="secondary">—</Text>,
                    },
                    {
                      title: '到期', dataIndex: 'next_action_at', key: 'due',
                      render: (v) => {
                        const { text, overdue } = fmtDueDays(v);
                        return <Tag color={overdue ? 'red' : 'orange'}>{text}</Tag>;
                      },
                    },
                    {
                      title: '操作', key: 'act', width: 96,
                      render: (_, r) => (
                        <Button size="small" type="primary" onClick={() => goFollow(r.customer_id)}>
                          去跟进
                        </Button>
                      ),
                    },
                  ]}
                />
              </div>
            )}

            {staleCount > 0 && (
              <div>
                <Text strong style={{ display: 'block', marginBottom: 8 }}>
                  <FireOutlined style={{ color: '#A4262C' }} /> 长期冷落 ({staleCount}, {'>'}14 天未联系)
                </Text>
                <Table<TodoStale>
                  rowKey="customer_id"
                  size="small"
                  pagination={{ pageSize: 5, size: 'small' }}
                  dataSource={todos?.stale ?? []}
                  columns={[
                    {
                      title: '客户', dataIndex: 'customer_name', key: 'name',
                      render: (name, r) => (
                        <Space direction="vertical" size={0}>
                          <Text strong>{name}</Text>
                          <Text type="secondary" style={{ fontSize: 11 }}>{r.customer_code}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: '上次跟进', dataIndex: 'last_follow_at', key: 'last',
                      render: (v) => <Text type="secondary">{fmtRelDays(v)}</Text>,
                    },
                    {
                      title: '冷落天数', dataIndex: 'days_since_follow', key: 'days',
                      render: (v) => v == null
                        ? <Tag color="red">从未跟进</Tag>
                        : <Tag color={v > 30 ? 'red' : 'orange'}>{v} 天</Tag>,
                    },
                    {
                      title: '操作', key: 'act', width: 96,
                      render: (_, r) => (
                        <Button size="small" onClick={() => goFollow(r.customer_id)}>去跟进</Button>
                      ),
                    },
                  ]}
                />
              </div>
            )}
          </Space>
        )}
      </Card>

      {/* 2. 年度目标进度 */}
      <Card
        title={
          <Space>
            <AimOutlined style={{ color: '#107C10' }} />
            <span>年度目标 · {targetProgress?.target_year ?? new Date().getFullYear()} 年度进度</span>
          </Space>
        }
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
      >
        {loading ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : targetProgress?.unbound || !targetProgress ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="主管未配置目标，或账号未绑定销售档案"
          />
        ) : !targetProgress.annual_sales_target && !targetProgress.annual_profit_target ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="主管尚未为你配置年度目标，请联系销售主管在「销售团队」里设置"
          />
        ) : (
          <Row gutter={[16, 20]}>
            {/* 销售额进度 */}
            {targetProgress.annual_sales_target != null && (
              <Col xs={24} md={12}>
                <Card size="small" style={{ background: '#f0fdf4', borderRadius: 10 }}>
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <div>
                        <Text type="secondary">销售额目标</Text>
                        <div style={{ fontSize: 20, fontWeight: 700 }}>
                          {fmtMoney(targetProgress.annual_sales_target)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <Text type="secondary">YTD 已完成</Text>
                        <div style={{ fontSize: 20, fontWeight: 700, color: '#107C10' }}>
                          {fmtMoney(targetProgress.ytd_sales)}
                        </div>
                      </div>
                    </Space>
                    <Progress
                      percent={Math.min(100, targetProgress.sales_progress_pct)}
                      strokeColor={{ '0%': '#107C10', '100%': '#0078D4' }}
                      status={targetProgress.sales_progress_pct >= 100 ? 'success' : 'active'}
                      format={() => `${targetProgress.sales_progress_pct.toFixed(1)}%`}
                    />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      日均还需达成{' '}
                      <Text strong style={{ color: '#dc2626' }}>
                        {fmtMoney(targetProgress.daily_sales_target_to_close)}
                      </Text>
                      {' '}/ 天
                    </Text>
                  </Space>
                </Card>
              </Col>
            )}

            {/* 毛利进度 */}
            {targetProgress.annual_profit_target != null && (
              <Col xs={24} md={12}>
                <Card size="small" style={{ background: '#eff6ff', borderRadius: 10 }}>
                  <Space direction="vertical" size={6} style={{ width: '100%' }}>
                    <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                      <div>
                        <Text type="secondary">毛利目标</Text>
                        <div style={{ fontSize: 20, fontWeight: 700 }}>
                          {fmtMoney(targetProgress.annual_profit_target)}
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <Text type="secondary">YTD 已完成</Text>
                        <div style={{ fontSize: 20, fontWeight: 700, color: '#0078D4' }}>
                          {fmtMoney(targetProgress.ytd_profit)}
                        </div>
                      </div>
                    </Space>
                    <Progress
                      percent={Math.min(100, targetProgress.profit_progress_pct)}
                      strokeColor={{ '0%': '#0078D4', '100%': '#107C10' }}
                      status={targetProgress.profit_progress_pct >= 100 ? 'success' : 'active'}
                      format={() => `${targetProgress.profit_progress_pct.toFixed(1)}%`}
                    />
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      日均还需达成{' '}
                      <Text strong style={{ color: '#dc2626' }}>
                        {fmtMoney(targetProgress.daily_profit_target_to_close)}
                      </Text>
                      {' '}/ 天
                    </Text>
                  </Space>
                </Card>
              </Col>
            )}

            {/* 底部统计行 */}
            <Col xs={24}>
              <Row gutter={[12, 0]}>
                <Col span={8}>
                  <Statistic
                    title="距年末剩余天数"
                    value={targetProgress.days_remaining_in_year}
                    suffix="天"
                    valueStyle={{ fontSize: 20, color: '#C19C00' }}
                  />
                </Col>
                {targetProgress.profit_margin_target != null && (
                  <Col span={8}>
                    <Statistic
                      title="毛利率目标"
                      value={Number(targetProgress.profit_margin_target).toFixed(1)}
                      suffix="%"
                      valueStyle={{ fontSize: 20, color: '#2B88D8' }}
                    />
                  </Col>
                )}
              </Row>
            </Col>
          </Row>
        )}
      </Card>

      {/* 3. 我的 KPI / 目标达成 */}
      <Card
        title={
          <Space>
            <AimOutlined style={{ color: '#0078D4' }} />
            <span>我的 KPI · {kpi?.target_year ?? new Date().getFullYear()} 年度目标</span>
          </Space>
        }
        bordered={false}
        style={{ borderRadius: 12 }}
      >
        {loading ? (
          <Skeleton active paragraph={{ rows: 3 }} />
        ) : (
          <Row gutter={[16, 16]}>
            <Col xs={24} lg={14}>
              <Card size="small" style={{ background: '#f8fafc', borderRadius: 10 }}>
                <Space direction="vertical" size={8} style={{ width: '100%' }}>
                  <Space style={{ width: '100%', justifyContent: 'space-between' }}>
                    <div>
                      <Text type="secondary">年度毛利目标</Text>
                      <div style={{ fontSize: 22, fontWeight: 700 }}>
                        {fmtMoney(kpi?.annual_target)}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <Text type="secondary">YTD 已完成</Text>
                      <div style={{ fontSize: 22, fontWeight: 700, color: '#107C10' }}>
                        {fmtMoney(kpi?.ytd_achievement)}
                      </div>
                    </div>
                  </Space>
                  <Progress
                    percent={Math.min(100, kpi?.progress_pct ?? 0)}
                    strokeColor={{ '0%': '#0078D4', '100%': '#107C10' }}
                    format={() => `${(kpi?.progress_pct ?? 0).toFixed(1)}%`}
                  />
                  <Text type="secondary">
                    还差 <Text strong style={{ color: '#dc2626' }}>{fmtMoney(kpi?.gap)}</Text>
                    {(kpi?.annual_target ?? 0) <= 0 && (
                      <Text type="warning" style={{ marginLeft: 8 }}>
                        (未设置年度目标, 请销售主管在'销售团队'里配置)
                      </Text>
                    )}
                  </Text>
                </Space>
              </Card>
            </Col>
            <Col xs={24} lg={10}>
              <Card size="small" style={{ borderRadius: 10 }}>
                <Text type="secondary" style={{ display: 'block', marginBottom: 8 }}>
                  本月 ({kpi?.month ?? '—'}) 指标
                </Text>
                <Row gutter={[12, 12]}>
                  <Col span={12}>
                    <Statistic title="新增商机" value={kpi?.month_new_opportunities ?? 0}
                      valueStyle={{ fontSize: 20, color: '#0078D4' }} />
                  </Col>
                  <Col span={12}>
                    <Statistic title="跟进次数" value={kpi?.month_follow_ups ?? 0}
                      valueStyle={{ fontSize: 20, color: '#2B88D8' }} />
                  </Col>
                  <Col span={12}>
                    <Statistic title="成单数" value={kpi?.month_deals ?? 0}
                      valueStyle={{ fontSize: 20, color: '#107C10' }} />
                  </Col>
                  <Col span={12}>
                    <Statistic title="签约金额" value={fmtMoney(kpi?.month_signed_amount)}
                      valueStyle={{ fontSize: 20, color: '#0078D4' }} />
                  </Col>
                </Row>
              </Card>
            </Col>
          </Row>
        )}
      </Card>
    </div>
  );
}

import { useEffect, useState } from 'react';
import {
  Card, Col, Row, Statistic, Skeleton, Space, Typography, Tag, Table,
  Empty, Alert, Progress, message as antdMessage,
} from 'antd';
import {
  RiseOutlined, FallOutlined, DollarOutlined, FundProjectionScreenOutlined,
  ThunderboltOutlined, PercentageOutlined, TeamOutlined,
} from '@ant-design/icons';
import { api } from '../api/axios';
import { STAGE_META, STAGE_ORDER } from '../constants/stage';

const { Title, Text } = Typography;

interface ManagerKpis {
  new_leads?: number;
  signing_rate?: number;
  payment_rate?: number;
  new_opportunities?: number;
  deal_rate?: number;
  collection_rate?: number;
  conversion_rate?: number;
  growth_rate?: number;
  opportunities?: number;
}

interface TeamFunnelRow {
  sales_name: string;
  lead?: number;
  contacting?: number;
  active?: number;
}

interface TeamProfit {
  year: number;
  team_annual_sales_target: number;
  team_annual_sales_achieved: number;
  team_annual_profit_target: number;
  team_annual_profit_achieved: number;
  team_profit_rate_target: number;
  team_profit_rate_actual: number;
}

interface StageAlert {
  id: number;
  customer_id: number;
  customer_name: string;
  current_stage: string;
  stuck_days: number;
}

function currentYearMonth(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  return `${d.getFullYear()}-${mm}`;
}

function fmtPct(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 100).toFixed(1)}%`;
}

function resolveKpi(kpis: ManagerKpis | null, ...keys: (keyof ManagerKpis)[]): number {
  if (!kpis) return 0;
  for (const k of keys) {
    const v = kpis[k];
    if (v != null) return v as number;
  }
  return 0;
}

const MOCK_FUNNEL: TeamFunnelRow[] = [
  { sales_name: '张三', lead: 3, contacting: 2, active: 4 },
  { sales_name: '李四', lead: 5, contacting: 1, active: 2 },
];

const STAGE_BG_COLORS: Record<string, string> = {
  lead: '#C8C6C4',
  contacting: '#2B88D8',
  active: '#107C10',
};

export default function ManagerPanorama() {
  const [month] = useState(currentYearMonth());
  const [kpis, setKpis] = useState<ManagerKpis | null>(null);
  const [kpisLoading, setKpisLoading] = useState(true);
  const [kpisMissing, setKpisMissing] = useState(false);

  const [teamFunnel, setTeamFunnel] = useState<TeamFunnelRow[]>([]);
  const [teamFunnelLoading, setTeamFunnelLoading] = useState(true);
  const [teamFunnelMock, setTeamFunnelMock] = useState(false);

  const [stageAlerts, setStageAlerts] = useState<StageAlert[]>([]);
  const [alertsLoading, setAlertsLoading] = useState(true);
  const [alertsMock, setAlertsMock] = useState(false);

  const [teamProfit, setTeamProfit] = useState<TeamProfit | null>(null);
  const [teamProfitLoading, setTeamProfitLoading] = useState(true);
  const [teamProfitMissing, setTeamProfitMissing] = useState(false);

  const loadKpis = async () => {
    setKpisLoading(true);
    setKpisMissing(false);
    try {
      const { data } = await api.get<ManagerKpis>('/api/metrics/dashboard', { params: { month } });
      setKpis(data);
    } catch {
      try {
        const { data } = await api.get<ManagerKpis>('/api/manager/kpis', { params: { month } });
        setKpis(data);
      } catch (e: any) {
        if (e?.response?.status === 404) setKpisMissing(true);
        else antdMessage.error(e?.response?.data?.detail || '加载 KPI 失败');
        setKpis(null);
      }
    } finally {
      setKpisLoading(false);
    }
  };

  const loadTeamFunnel = async () => {
    setTeamFunnelLoading(true);
    setTeamFunnelMock(false);
    try {
      const { data } = await api.get<TeamFunnelRow[]>('/api/metrics/team-funnel', { params: { month } });
      const rows = Array.isArray(data) ? data : (data as any)?.items || [];
      if (rows.length > 0) {
        setTeamFunnel(rows);
      } else {
        setTeamFunnel(MOCK_FUNNEL);
        setTeamFunnelMock(true);
      }
    } catch {
      setTeamFunnel(MOCK_FUNNEL);
      setTeamFunnelMock(true);
    } finally {
      setTeamFunnelLoading(false);
    }
  };

  const loadStageAlerts = async () => {
    setAlertsLoading(true);
    setAlertsMock(false);
    try {
      const { data } = await api.get<StageAlert[]>('/api/metrics/stage-alerts');
      const rows = Array.isArray(data) ? data : (data as any)?.items || [];
      setStageAlerts(rows);
    } catch {
      setStageAlerts([]);
      setAlertsMock(true);
    } finally {
      setAlertsLoading(false);
    }
  };

  const loadTeamProfit = async () => {
    setTeamProfitLoading(true);
    setTeamProfitMissing(false);
    try {
      const { data } = await api.get<TeamProfit>('/api/metrics/team-profit');
      setTeamProfit(data);
    } catch (e: any) {
      if (e?.response?.status === 404) setTeamProfitMissing(true);
      setTeamProfit(null);
    } finally {
      setTeamProfitLoading(false);
    }
  };

  useEffect(() => {
    loadKpis();
    loadTeamFunnel();
    loadStageAlerts();
    loadTeamProfit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const alertCols = [
    {
      title: '客户', dataIndex: 'customer_name', ellipsis: true,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: '当前 Stage', dataIndex: 'current_stage', width: 130,
      render: (s: string) => {
        const meta = STAGE_META[s];
        return meta ? <Tag color={meta.color}>{meta.emoji} {meta.label}</Tag> : <Tag>{s}</Tag>;
      },
    },
    {
      title: '卡了多久', dataIndex: 'stuck_days', width: 100,
      render: (d: number) => (
        <Tag color={d > 14 ? 'red' : d > 7 ? 'orange' : 'default'}>{d} 天</Tag>
      ),
    },
    {
      title: '操作', width: 100, fixed: 'right' as const,
      render: (_: unknown, r: StageAlert) => (
        <a onClick={() => antdMessage.info(`跳转到客户 #${r.customer_id}`)}>查看客户</a>
      ),
    },
  ];

  const maxFunnelTotal = Math.max(1,
    ...teamFunnel.map((r) => STAGE_ORDER.reduce((sum, k) => sum + ((r as any)[k] || 0), 0))
  );

  return (
    <div className="page-fade">
      {/* Hero banner */}
      <Card
        bordered={false}
        style={{
          borderRadius: 4,
          marginBottom: 16,
          background: '#FFFFFF',
          border: '1px solid #E1DFDD',
          color: '#1F2937',
        }}
        styles={{ body: { padding: 20 } }}
      >
        <Space direction="vertical" size={4}>
          <Title level={3} style={{ color: '#1F2937', margin: 0 }}>
            <FundProjectionScreenOutlined style={{ marginRight: 8, color: '#0078D4' }} />
            销售主管 · 全景视图
          </Title>
          <Text style={{ color: '#6B7280' }}>
            {month} · 新增商机 / 转化率 / 签单率 / 增长率 / 回款率
          </Text>
        </Space>
      </Card>

      {kpisMissing && (
        <Alert
          type="info" showIcon style={{ marginBottom: 16 }}
          message="KPI 接口待上线"
          description={<>后端 <code>GET /api/metrics/dashboard</code> 尚未实现，显示占位。</>}
        />
      )}

      {/* 5 KPI cards */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} sm={12} lg={24 / 5}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <Statistic
                title={<Space><ThunderboltOutlined /> 新增商机</Space>}
                value={resolveKpi(kpis, 'new_opportunities', 'new_leads', 'opportunities')}
                valueStyle={{ color: '#0078D4' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={24 / 5}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <Statistic
                title={<Space><PercentageOutlined /> 转化率</Space>}
                value={fmtPct(resolveKpi(kpis, 'conversion_rate'))}
                valueStyle={{ color: '#2B88D8' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={24 / 5}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <Statistic
                title="签单率"
                value={fmtPct(resolveKpi(kpis, 'deal_rate', 'signing_rate'))}
                valueStyle={{ color: '#005A9E' }}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={24 / 5}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <Statistic
                title="增长率 (本月 vs 上月)"
                value={fmtPct(resolveKpi(kpis, 'growth_rate'))}
                valueStyle={{ color: resolveKpi(kpis, 'growth_rate') >= 0 ? '#107C10' : '#A4262C' }}
                prefix={resolveKpi(kpis, 'growth_rate') >= 0 ? <RiseOutlined /> : <FallOutlined />}
              />
            )}
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={24 / 5}>
          <Card bordered={false} style={{ borderRadius: 12 }}>
            {kpisLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
              <Statistic
                title="回款率"
                value={fmtPct(resolveKpi(kpis, 'collection_rate', 'payment_rate'))}
                prefix={<DollarOutlined />}
                valueStyle={{ color: '#C19C00' }}
              />
            )}
          </Card>
        </Col>
      </Row>

      {/* Team Profit Rate */}
      <Card
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
        title={<Space><PercentageOutlined />销售团队利润 概览 {teamProfit ? <Tag>{teamProfit.year} 年</Tag> : null}</Space>}
        extra={teamProfitMissing ? <Tag color="orange">接口待上线</Tag> : null}
      >
        {teamProfitLoading ? <Skeleton active /> : !teamProfit ? (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (() => {
          const rt = teamProfit.team_profit_rate_target * 100;
          const ra = teamProfit.team_profit_rate_actual * 100;
          const diff = ra - rt;
          const salesPct = teamProfit.team_annual_sales_target > 0
            ? Math.round((teamProfit.team_annual_sales_achieved / teamProfit.team_annual_sales_target) * 100)
            : 0;
          const profitPct = teamProfit.team_annual_profit_target > 0
            ? Math.round((teamProfit.team_annual_profit_achieved / teamProfit.team_annual_profit_target) * 100)
            : 0;
          return (
            <Row gutter={[24, 16]}>
              <Col xs={24} md={8}>
                <Statistic
                  title="利润率目标"
                  value={rt}
                  precision={1}
                  suffix="%"
                  valueStyle={{ color: '#0078D4' }}
                />
                <Statistic
                  title="实际利润率"
                  value={ra}
                  precision={1}
                  suffix="%"
                  valueStyle={{ color: diff >= 0 ? '#107C10' : '#A4262C' }}
                  prefix={diff >= 0 ? <RiseOutlined /> : <FallOutlined />}
                />
                <Text type={diff >= 0 ? 'success' : 'danger'} style={{ fontSize: 12 }}>
                  {diff >= 0 ? '↑' : '↓'}{Math.abs(diff).toFixed(1)}% vs 目标
                </Text>
                <Progress
                  percent={Math.min(100, Math.max(0, Math.round(ra)))}
                  success={{ percent: Math.min(100, Math.max(0, Math.round(rt))) }}
                  status={diff >= 0 ? 'success' : 'active'}
                  style={{ marginTop: 8 }}
                />
              </Col>
              <Col xs={24} md={8}>
                <Text type="secondary">销售额 (YTD / 目标)</Text>
                <Title level={4} style={{ margin: '4px 0' }}>
                  ¥{teamProfit.team_annual_sales_achieved.toLocaleString()}
                  <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
                    {' '}/ ¥{teamProfit.team_annual_sales_target.toLocaleString()}
                  </Text>
                </Title>
                <Progress percent={Math.min(100, salesPct)} status="active" />
                <Text type="secondary" style={{ fontSize: 12 }}>{salesPct}% 达成</Text>
              </Col>
              <Col xs={24} md={8}>
                <Text type="secondary">利润 (YTD / 目标)</Text>
                <Title level={4} style={{ margin: '4px 0' }}>
                  ¥{teamProfit.team_annual_profit_achieved.toLocaleString()}
                  <Text type="secondary" style={{ fontSize: 13, fontWeight: 400 }}>
                    {' '}/ ¥{teamProfit.team_annual_profit_target.toLocaleString()}
                  </Text>
                </Title>
                <Progress percent={Math.min(100, profitPct)} status="active" strokeColor="#C19C00" />
                <Text type="secondary" style={{ fontSize: 12 }}>{profitPct}% 达成</Text>
              </Col>
            </Row>
          );
        })()}
      </Card>

      {/* Team Funnel */}
      <Card
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
        title={<Space><TeamOutlined />团队漏斗对比</Space>}
        extra={teamFunnelMock ? <Tag color="orange">示例数据 / 接口待上线</Tag> : null}
      >
        {teamFunnelLoading ? <Skeleton active /> : teamFunnel.length === 0 ? (
          <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : (
          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <Space wrap>
              {STAGE_ORDER.map((k) => (
                <Tag key={k} color={STAGE_META[k].color}>{STAGE_META[k].emoji} {STAGE_META[k].label}</Tag>
              ))}
            </Space>
            {teamFunnel.map((row) => {
              const total = STAGE_ORDER.reduce((s, k) => s + ((row as any)[k] || 0), 0);
              return (
                <div key={row.sales_name} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 80, flexShrink: 0, fontWeight: 600 }}>{row.sales_name}</div>
                  <div style={{ flex: 1, display: 'flex', height: 24, borderRadius: 4, overflow: 'hidden', background: '#f0f0f0' }}>
                    {STAGE_ORDER.map((k) => {
                      const count = (row as any)[k] || 0;
                      const pct = total > 0 ? (count / maxFunnelTotal) * 100 : 0;
                      if (pct === 0) return null;
                      return (
                        <div
                          key={k}
                          title={`${STAGE_META[k].label}: ${count}`}
                          style={{
                            width: `${pct}%`,
                            background: STAGE_BG_COLORS[k],
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 11,
                            color: '#333',
                            minWidth: count > 0 ? 20 : 0,
                            transition: 'width 0.3s',
                          }}
                        >
                          {count > 0 ? count : ''}
                        </div>
                      );
                    })}
                  </div>
                  <Text type="secondary" style={{ width: 50, textAlign: 'right', flexShrink: 0 }}>
                    {total} 客户
                  </Text>
                </div>
              );
            })}
          </Space>
        )}
      </Card>

      {/* Stage Alerts */}
      <Card
        bordered={false}
        style={{ borderRadius: 12, marginBottom: 16 }}
        title="异常告警"
        extra={alertsMock ? <Tag color="orange">接口待上线</Tag> : null}
      >
        {alertsLoading ? <Skeleton active /> : stageAlerts.length === 0 ? (
          <Empty
            description={alertsMock ? '后端 GET /api/metrics/stage-alerts 待上线' : '暂无异常告警'}
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          />
        ) : (
          <Table<StageAlert>
            rowKey="id"
            loading={alertsLoading}
            columns={alertCols}
            dataSource={stageAlerts}
            scroll={{ x: 600 }}
            pagination={false}
            size="small"
          />
        )}
      </Card>
    </div>
  );
}

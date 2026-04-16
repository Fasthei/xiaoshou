import { useEffect, useState } from 'react';
import { Card, Col, Empty, Progress, Row, Skeleton, Space, Statistic, Tag, Typography } from 'antd';
import { Link } from 'react-router-dom';
import { RocketOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import { useAuth } from '../contexts/AuthContext';

const { Title, Text } = Typography;

interface SalesPerf {
  id: number;
  name: string;
  customer_count: number;
  ytd_gmv: number;
  target_gmv: number;
  progress_pct: number;
}

function currentMonthStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function normalize(s: string | undefined | null): string {
  return (s || '').trim().toLowerCase();
}

/**
 * 宽松匹配: 优先 name 完全相等, 否则 email 前缀 (user@x) 匹配 name, 再否则 name 互为包含关系。
 */
function matchMine(rows: SalesPerf[], userName?: string, userEmail?: string): SalesPerf | null {
  if (!rows.length) return null;
  const name = normalize(userName);
  const emailLocal = normalize(userEmail?.split('@')[0]);

  if (name) {
    const exact = rows.find((r) => normalize(r.name) === name);
    if (exact) return exact;
  }
  if (emailLocal) {
    const byEmail = rows.find((r) => normalize(r.name) === emailLocal);
    if (byEmail) return byEmail;
  }
  if (name) {
    const contains = rows.find(
      (r) => normalize(r.name).includes(name) || name.includes(normalize(r.name)),
    );
    if (contains) return contains;
  }
  return null;
}

export default function SalesHome() {
  const { user } = useAuth();
  const year = new Date().getFullYear();
  const [loading, setLoading] = useState(true);
  const [mine, setMine] = useState<SalesPerf | null>(null);
  const [missing, setMissing] = useState(false);

  const load = async () => {
    setLoading(true);
    setMissing(false);
    try {
      const { data } = await api.get<SalesPerf[] | { items: SalesPerf[] }>(
        '/api/manager/sales-performance',
        { params: { month: currentMonthStr() } },
      );
      const rows: SalesPerf[] = Array.isArray(data) ? data : (data as any)?.items || [];
      const hit = matchMine(rows, user?.name, user?.email);
      if (!hit) setMissing(true);
      setMine(hit);
    } catch (e: any) {
      if (e?.response?.status === 404) setMissing(true);
      setMine(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.name, user?.email]);

  const gap =
    mine && mine.target_gmv > 0 ? +(mine.target_gmv - mine.ytd_gmv).toFixed(2) : 0;
  const progressPct = mine ? Math.max(0, Math.min(100, Math.round(mine.progress_pct))) : 0;

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      {/* Hero banner */}
      <Card
        style={{
          background: 'linear-gradient(135deg, #4f46e5 0%, #ec4899 100%)',
          color: '#fff',
          border: 'none',
        }}
        styles={{ body: { padding: '28px 32px' } }}
      >
        <Space direction="vertical" size={6}>
          <Space align="center" size={12}>
            <RocketOutlined style={{ fontSize: 28, color: '#fff' }} />
            <Title level={3} style={{ color: '#fff', margin: 0 }}>
              销售个人工作台 · {year}
            </Title>
          </Space>
          <Text style={{ color: 'rgba(255,255,255,0.85)' }}>
            {user?.name ? `你好，${user.name}` : '你好'} · 今日目标达成一步一步来
          </Text>
        </Space>
      </Card>

      {loading ? (
        <Card>
          <Skeleton active />
        </Card>
      ) : missing || !mine ? (
        <Card>
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" size={4}>
                <Text>没有您的目标数据</Text>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  请联系销售主管在后台设置您的年度目标 (annual_profit_target)
                </Text>
              </Space>
            }
          />
        </Card>
      ) : (
        <>
          <Card title={<Space>🎯 {year} 年度目标进度</Space>}>
            <Row gutter={16}>
              <Col xs={24} sm={12} md={8}>
                <Statistic
                  title="年度目标"
                  value={mine.target_gmv}
                  prefix="¥"
                  precision={2}
                />
              </Col>
              <Col xs={24} sm={12} md={8}>
                <Statistic
                  title="YTD 业绩"
                  value={mine.ytd_gmv}
                  prefix="¥"
                  precision={2}
                  valueStyle={{ color: '#16a34a' }}
                />
              </Col>
              <Col xs={24} sm={12} md={8}>
                <Statistic
                  title="距达标缺口"
                  value={gap > 0 ? gap : 0}
                  prefix="¥"
                  precision={2}
                  valueStyle={{ color: gap > 0 ? '#ef4444' : '#16a34a' }}
                  suffix={gap <= 0 ? ' ✅ 已达标' : undefined}
                />
              </Col>
            </Row>
            <div style={{ marginTop: 24 }}>
              <Text type="secondary" style={{ fontSize: 12 }}>进度</Text>
              <Progress
                percent={progressPct}
                status={progressPct >= 100 ? 'success' : 'active'}
                strokeColor={{ '0%': '#4f46e5', '100%': '#ec4899' }}
              />
            </div>
            <div style={{ marginTop: 12 }}>
              <Space size={12}>
                <Tag color="blue">客户数 {mine.customer_count}</Tag>
                <Tag color="purple">Sales ID #{mine.id}</Tag>
              </Space>
            </div>
          </Card>

          <Card size="small">
            <Space style={{ width: '100%', justifyContent: 'space-between' }}>
              <Text type="secondary">想看你手上的客户？</Text>
              <Link to="/customers">
                去客户管理 <ArrowRightOutlined />
              </Link>
            </Space>
          </Card>
        </>
      )}
    </Space>
  );
}

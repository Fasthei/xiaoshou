import { useEffect, useState } from 'react';
import { Card, Table, Tag, Typography, Progress, Space, DatePicker, Button, Empty, Result } from 'antd';
import { ReloadOutlined, AlertOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { AxiosError } from 'axios';
import { api } from '../api/axios';

const { Title, Text } = Typography;

interface RuleStatus {
  rule_id: number;
  rule_name: string;
  threshold_type: string;
  threshold_value: number;
  actual: number;
  pct: number;
  triggered: boolean;
  account_name?: string | null;
  provider?: string | null;
  external_project_id?: string | null;
}

export default function Alerts() {
  const [rows, setRows] = useState<RuleStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [month, setMonth] = useState<Dayjs | null>(dayjs());
  const [error, setError] = useState<AxiosError<{ detail?: string }> | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<RuleStatus[]>('/api/bridge/alerts', {
        params: { month: month?.format('YYYY-MM') },
      });
      setRows(data);
    } catch (err) {
      setError(err as AxiosError<{ detail?: string }>);
      setRows([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [month]);

  if (error) {
    const status = error.response?.status;
    const detail = error.response?.data?.detail || error.message || '稍后再试';
    return (
      <div className="page-fade">
        <Card bordered={false} style={{ borderRadius: 12 }}>
          <Result
            status="500"
            title="云管暂不可达"
            subTitle={`${status ? status + ' · ' : ''}${detail}`}
            extra={
              <Space>
                <DatePicker picker="month" value={month} onChange={setMonth} />
                <Button type="primary" icon={<ReloadOutlined />} onClick={load}>重试</Button>
              </Space>
            }
          />
        </Card>
      </div>
    );
  }

  const triggered = rows.filter((r) => r.triggered).length;
  const near = rows.filter((r) => !r.triggered && (r.pct || 0) >= 80).length;

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 12, marginBottom: 16,
          background: 'linear-gradient(120deg, #fb7185 0%, #ef4444 50%, #f97316 100%)',
          color: 'white',
        }}
        styles={{ body: { padding: 28 } }}
      >
        <Space direction="vertical" size={4}>
          <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>ALERTS · 预警</Text>
          <Title level={2} style={{ color: 'white', margin: 0 }}>
            <AlertOutlined /> 预警监控
          </Title>
          <Text style={{ color: 'rgba(255,255,255,0.85)' }}>
            来自云管 cloudcost alerts/rule-status — 已触发 {triggered} · 接近阈值 {near}
          </Text>
        </Space>
      </Card>

      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>规则状态</Title>
          <Space>
            <DatePicker picker="month" value={month} onChange={setMonth} />
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Space>
        </Space>

        {rows.length === 0 && !loading ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="该月无预警规则或云管未配置" />
        ) : (
          <Table<RuleStatus>
            rowKey="rule_id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
            columns={[
              { title: '规则', dataIndex: 'rule_name' },
              {
                title: '类型', dataIndex: 'threshold_type', width: 180,
                render: (v) => <Tag color="geekblue">{v}</Tag>,
              },
              { title: '账号', dataIndex: 'account_name', width: 180 },
              { title: '阈值', dataIndex: 'threshold_value', width: 100 },
              { title: '实际', dataIndex: 'actual', width: 100 },
              {
                title: '完成度', dataIndex: 'pct', width: 200,
                render: (v: number) => (
                  <Progress
                    percent={Math.min(Math.round(v), 100)} size="small"
                    status={v >= 100 ? 'exception' : v >= 80 ? 'active' : 'normal'}
                  />
                ),
              },
              {
                title: '状态', dataIndex: 'triggered', width: 110,
                render: (t: boolean, r) =>
                  t ? <Tag color="red">已触发</Tag>
                    : (r.pct || 0) >= 80 ? <Tag color="orange">接近</Tag>
                    : <Tag color="green">正常</Tag>,
              },
            ]}
          />
        )}
      </Card>
    </div>
  );
}

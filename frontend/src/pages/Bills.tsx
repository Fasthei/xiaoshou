import { useEffect, useState } from 'react';
import { Card, Table, Tag, Typography, Space, DatePicker, Button, Select, Statistic, Row, Col } from 'antd';
import { ReloadOutlined, DollarOutlined } from '@ant-design/icons';
import dayjs, { Dayjs } from 'dayjs';
import { api } from '../api/axios';

const { Title, Text } = Typography;

interface Bill {
  id: number;
  month: string;
  category_id?: number;
  provider: string;
  original_cost: number;
  markup_rate: number;
  final_cost: number;
  adjustment: number;
  status: string;
  confirmed_at?: string | null;
  notes?: string | null;
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  draft: 'default', confirmed: 'blue', paid: 'green',
};

export default function Bills() {
  const [rows, setRows] = useState<Bill[]>([]);
  const [loading, setLoading] = useState(false);
  const [month, setMonth] = useState<Dayjs | null>(dayjs());
  const [status, setStatus] = useState<string | undefined>();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Bill[]>('/api/bridge/bills', {
        params: { month: month?.format('YYYY-MM'), status, page_size: 100 },
      });
      setRows(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [month, status]);

  const total = rows.reduce((s, b) => s + Number(b.final_cost || 0), 0);
  const confirmed = rows.filter((b) => b.status === 'confirmed' || b.status === 'paid')
    .reduce((s, b) => s + Number(b.final_cost || 0), 0);

  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 12, marginBottom: 16,
          background: 'linear-gradient(120deg, #10b981 0%, #0ea5e9 100%)',
          color: 'white',
        }}
        styles={{ body: { padding: 24 } }}
      >
        <Row gutter={24}>
          <Col xs={24} md={12}>
            <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>BILLS · 账单</Text>
            <Title level={2} style={{ color: 'white', margin: '4px 0 0' }}>
              <DollarOutlined /> 月度账单
            </Title>
            <Text style={{ color: 'rgba(255,255,255,0.8)' }}>代理自云管 cloudcost</Text>
          </Col>
          <Col xs={24} md={6}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>本月应收</span>}
              value={total} precision={2} prefix="¥"
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
          <Col xs={24} md={6}>
            <Statistic title={<span style={{ color: 'rgba(255,255,255,0.85)' }}>已确认 / 已付</span>}
              value={confirmed} precision={2} prefix="¥"
              valueStyle={{ color: '#fff', fontWeight: 700 }} />
          </Col>
        </Row>
      </Card>

      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>账单明细</Title>
          <Space>
            <DatePicker picker="month" value={month} onChange={setMonth} />
            <Select placeholder="状态" allowClear style={{ width: 120 }} value={status} onChange={setStatus}
              options={['draft', 'confirmed', 'paid'].map((v) => ({ value: v, label: v }))} />
            <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          </Space>
        </Space>
        <Table<Bill>
          rowKey="id" loading={loading} dataSource={rows} pagination={{ pageSize: 20 }}
          columns={[
            { title: '月份', dataIndex: 'month', width: 110 },
            { title: '云厂商', dataIndex: 'provider', width: 100,
              render: (v: string) => <Tag color="blue">{v}</Tag> },
            { title: '原始成本', dataIndex: 'original_cost', width: 120,
              render: (v: number) => `¥${Number(v).toFixed(2)}` },
            { title: '加价倍率', dataIndex: 'markup_rate', width: 110,
              render: (v: number) => `${Number(v).toFixed(2)}x` },
            { title: '调整', dataIndex: 'adjustment', width: 100,
              render: (v: number) => `¥${Number(v).toFixed(2)}` },
            { title: '最终', dataIndex: 'final_cost', width: 120,
              render: (v: number) => <Text strong>¥{Number(v).toFixed(2)}</Text> },
            { title: '状态', dataIndex: 'status', width: 110,
              render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag> },
            { title: '创建', dataIndex: 'created_at', width: 170 },
          ]}
        />
      </Card>
    </div>
  );
}

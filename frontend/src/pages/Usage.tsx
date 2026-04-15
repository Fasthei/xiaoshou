import { useState } from 'react';
import { Button, Card, Empty, Form, InputNumber, Space, Statistic, Table, Typography } from 'antd';
import { SearchOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { UsageRecord } from '../types';

const { Title } = Typography;

interface Summary {
  total_amount?: string | number;
  total_cost?: string | number;
  record_count?: number;
  [k: string]: unknown;
}

export default function Usage() {
  const [customerId, setCustomerId] = useState<number | null>(null);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [records, setRecords] = useState<UsageRecord[]>([]);
  const [loading, setLoading] = useState(false);

  const search = async () => {
    if (!customerId) return;
    setLoading(true);
    try {
      const [sumR, listR] = await Promise.all([
        api.get<Summary>(`/api/usage/customer/${customerId}/summary`),
        api.get<UsageRecord[] | { items?: UsageRecord[] }>(`/api/usage/customer/${customerId}`),
      ]);
      setSummary(sumR.data);
      const list = Array.isArray(listR.data) ? listR.data : (listR.data?.items || []);
      setRecords(list);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <Space direction="vertical" size="large" style={{ width: '100%' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Title level={4} style={{ margin: 0 }}>用量查询</Title>
        </Space>

        <Form layout="inline" onFinish={search}>
          <Form.Item label="客户 ID" required>
            <InputNumber min={1} value={customerId ?? undefined} onChange={(v) => setCustomerId(v as number | null)} />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" icon={<SearchOutlined />} loading={loading} disabled={!customerId}>
              查询
            </Button>
          </Form.Item>
        </Form>

        {summary ? (
          <Space size="large">
            <Statistic title="记录数" value={Number(summary.record_count || 0)} />
            <Statistic title="总用量" value={Number(summary.total_amount || 0)} precision={2} />
            <Statistic title="总成本 (¥)" value={Number(summary.total_cost || 0)} precision={2} />
          </Space>
        ) : null}

        {customerId && !records.length && !loading ? <Empty description="暂无用量记录" /> : null}

        {records.length ? (
          <Table<UsageRecord>
            rowKey="id"
            loading={loading}
            dataSource={records}
            pagination={{ pageSize: 20, showTotal: (t) => `共 ${t} 条` }}
            columns={[
              { title: '日期', dataIndex: 'usage_date', width: 140 },
              { title: '货源 ID', dataIndex: 'resource_id', width: 100 },
              { title: '用量', dataIndex: 'usage_amount', width: 120 },
              { title: '单位', dataIndex: 'usage_unit', width: 80 },
              { title: '成本', dataIndex: 'cost', width: 120 },
            ]}
          />
        ) : null}
      </Space>
    </Card>
  );
}

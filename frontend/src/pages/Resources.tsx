import { useEffect, useState } from 'react';
import { Button, Card, Input, Select, Space, Table, Tag, Typography, message } from 'antd';
import { CloudDownloadOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { Pagination, Resource } from '../types';

const { Title } = Typography;

const STATUS_COLOR: Record<string, string> = {
  AVAILABLE: 'green', ALLOCATED: 'blue', EXPIRED: 'default', FROZEN: 'red',
};

export default function Resources() {
  const [rows, setRows] = useState<Resource[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [provider, setProvider] = useState<string | undefined>();
  const [availOnly, setAvailOnly] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get<Pagination<Resource>>('/api/resources', {
        params: {
          page, page_size: pageSize,
          keyword: keyword || undefined,
          cloud_provider: provider,
          available_only: availOnly || undefined,
        },
      });
      setRows(data.items); setTotal(data.total);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [page, pageSize, availOnly]);

  const columns = [
    { title: '货源编号', dataIndex: 'resource_code', width: 170 },
    { title: '类型', dataIndex: 'resource_type', width: 100 },
    { title: '云厂商', dataIndex: 'cloud_provider', width: 100 },
    { title: '账号', dataIndex: 'account_name' },
    { title: '总量', dataIndex: 'total_quantity', width: 80 },
    { title: '已分配', dataIndex: 'allocated_quantity', width: 80 },
    { title: '可用', dataIndex: 'available_quantity', width: 80 },
    { title: '单位成本', dataIndex: 'unit_cost', width: 100 },
    { title: '建议价', dataIndex: 'suggested_price', width: 100 },
    {
      title: '状态', dataIndex: 'resource_status', width: 110,
      render: (s: string) => <Tag color={STATUS_COLOR[s] || 'default'}>{s}</Tag>,
    },
  ];

  return (
    <Card>
      <Space style={{ marginBottom: 16, width: '100%', justifyContent: 'space-between' }}>
        <Title level={4} style={{ margin: 0 }}>货源管理</Title>
        <Space>
          <Input
            placeholder="货源编号/账号"
            prefix={<SearchOutlined />}
            allowClear
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
            onPressEnter={() => { setPage(1); load(); }}
            style={{ width: 220 }}
          />
          <Select
            placeholder="云厂商" allowClear style={{ width: 120 }}
            value={provider}
            onChange={(v) => { setProvider(v); setPage(1); load(); }}
            options={['AZURE', 'AWS', 'GCP', 'ALIYUN'].map((v) => ({ value: v, label: v }))}
          />
          <Select
            style={{ width: 140 }}
            value={availOnly ? 'avail' : 'all'}
            onChange={(v) => setAvailOnly(v === 'avail')}
            options={[{ value: 'all', label: '全部货源' }, { value: 'avail', label: '仅可分配' }]}
          />
          <Button icon={<ReloadOutlined />} onClick={load}>刷新</Button>
          <Button
            icon={<CloudDownloadOutlined />} loading={syncing}
            onClick={async () => {
              setSyncing(true);
              try {
                const { data } = await api.post('/api/sync/resources/from-cloudcost');
                message.success(`从云管镜像：拉取 ${data.pulled} · 新增 ${data.created} · 更新 ${data.updated}`);
                load();
              } finally { setSyncing(false); }
            }}
          >从云管同步</Button>
        </Space>
      </Space>
      <Table<Resource>
        rowKey="id" loading={loading} columns={columns} dataSource={rows}
        scroll={{ x: 1200 }}
        pagination={{
          current: page, pageSize, total, showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => { setPage(p); setPageSize(ps); },
        }}
      />
    </Card>
  );
}

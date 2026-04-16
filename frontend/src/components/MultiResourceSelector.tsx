import { useEffect, useState } from 'react';
import { Button, Col, Input, InputNumber, Row, Select, Space, Typography, message } from 'antd';
import { MinusCircleOutlined, PlusOutlined } from '@ant-design/icons';
import { api } from '../api/axios';
import type { Resource } from '../types';

const { Text } = Typography;

export interface ResourceLine {
  resource_id: number;
  end_user_label?: string;
  quantity?: number;
}

interface Props {
  value?: ResourceLine[];
  onChange?: (v: ResourceLine[]) => void;
  customerType?: 'direct' | 'channel';
}

/**
 * MultiResourceSelector — 订单多货源行编辑器。
 *
 * - 一次性拉取 resources (page_size=200)。
 * - 每行: 货源 Select + quantity InputNumber + (渠道客户) end_user_label Input + 删除。
 * - 至少 1 行，否则下方显示 warning Text（仅提示；真正 required 由外层 Form.Item rules 控制）。
 * - 调用方自行用 <Form.Item> 包裹（取 value/onChange）。
 */
export default function MultiResourceSelector({ value, onChange, customerType }: Props) {
  const [resources, setResources] = useState<Resource[]>([]);
  const [loading, setLoading] = useState(false);
  const lines: ResourceLine[] = value ?? [];

  useEffect(() => {
    setLoading(true);
    api
      .get('/api/resources', { params: { page_size: 200 } })
      .then(({ data }) => setResources(data.items || []))
      .catch(() => message.error('货源列表加载失败'))
      .finally(() => setLoading(false));
  }, []);

  const emit = (next: ResourceLine[]) => onChange?.(next);

  const updateLine = (idx: number, patch: Partial<ResourceLine>) => {
    const next = lines.map((l, i) => (i === idx ? { ...l, ...patch } : l));
    emit(next);
  };

  const addLine = () => {
    emit([...lines, { resource_id: 0 as unknown as number, quantity: 1 }]);
  };

  const removeLine = (idx: number) => {
    emit(lines.filter((_, i) => i !== idx));
  };

  const options = resources.map((r) => ({
    value: r.id,
    label:
      `${r.resource_code} · ${r.account_name ?? '-'}` +
      (r.cloud_provider ? ` (${r.cloud_provider})` : ''),
  }));

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={8}>
      {lines.map((line, idx) => (
        <Row key={idx} gutter={8} align="middle" wrap={false}>
          <Col flex="auto">
            <Select
              showSearch
              loading={loading}
              placeholder="选货源"
              value={line.resource_id || undefined}
              options={options}
              filterOption={(input, opt) =>
                String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              onChange={(v) => updateLine(idx, { resource_id: v })}
              style={{ width: '100%' }}
            />
          </Col>
          <Col flex="90px">
            <InputNumber
              min={1}
              value={line.quantity ?? 1}
              onChange={(v) => updateLine(idx, { quantity: v ?? 1 })}
              style={{ width: '100%' }}
              placeholder="数量"
            />
          </Col>
          {customerType === 'channel' && (
            <Col flex="200px">
              <Input
                placeholder="终端用户标签"
                value={line.end_user_label ?? ''}
                onChange={(e) => updateLine(idx, { end_user_label: e.target.value })}
              />
            </Col>
          )}
          <Col flex="28px">
            <Button
              type="text"
              icon={<MinusCircleOutlined />}
              onClick={() => removeLine(idx)}
              aria-label="删除该行货源"
            />
          </Col>
        </Row>
      ))}

      <Button type="dashed" icon={<PlusOutlined />} onClick={addLine} block>
        添加货源
      </Button>

      {lines.length === 0 && (
        <Text type="warning" style={{ fontSize: 12 }}>
          至少选一个货源
        </Text>
      )}
    </Space>
  );
}

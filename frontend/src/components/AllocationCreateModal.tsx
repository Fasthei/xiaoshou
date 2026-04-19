import { useEffect, useState } from 'react';
import { Modal, Form, Select, InputNumber, Slider, Row, Col, Statistic, Space, Typography, message } from 'antd';
import { api } from '../api/axios';
import type { Customer, Resource } from '../types';

const { Text } = Typography;

export default function AllocationCreateModal({
  open, onClose, onCreated,
}: { open: boolean; onClose: () => void; onCreated?: () => void }) {
  const [form] = Form.useForm();
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [qty, setQty] = useState(1);
  const [cost, setCost] = useState(1);
  const [markup, setMarkup] = useState(30); // %
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    // Backend caps page_size at 100 — fetch 100 each, enough for dropdown.
    // TODO: switch to remote-search dropdown when inventory grows beyond 100.
    api.get('/api/customers', { params: { page_size: 100 } })
      .then(({ data }) => setCustomers(data.items || []))
      .catch(() => message.error('客户列表加载失败'));
    api.get('/api/resources', { params: { page_size: 100 } })
      .then(({ data }) => setResources(data.items || []))
      .catch(() => message.error('货源列表加载失败'));
  }, [open]);

  const unitPrice = +(cost * (1 + markup / 100)).toFixed(2);
  const totalCost = +(cost * qty).toFixed(2);
  const totalPrice = +(unitPrice * qty).toFixed(2);
  const profit = +(totalPrice - totalCost).toFixed(2);
  const profitRate = totalCost > 0 ? +((profit / totalCost) * 100).toFixed(1) : 0;

  const submit = async () => {
    const v = await form.validateFields();
    setSaving(true);
    try {
      await api.post('/api/allocations', {
        customer_id: v.customer_id,
        resource_id: v.resource_id,
        allocated_quantity: qty,
        unit_cost: cost,
        unit_price: unitPrice,
        total_cost: totalCost,
        total_price: totalPrice,
        profit_amount: profit,
        profit_rate: profitRate,
        allocation_code: `ALLOC-${Date.now().toString(36).toUpperCase()}`,
        allocation_status: 'PENDING',
      });
      message.success('订单已创建，云管会自动拉取同步');
      onCreated?.();
      onClose();
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="新建订单 · 毛利实时计算" open={open} onOk={submit} onCancel={onClose}
      width={640} confirmLoading={saving} destroyOnClose
    >
      <Form form={form} layout="vertical">
        <Row gutter={12}>
          <Col span={12}>
            <Form.Item name="customer_id" label="客户" rules={[{ required: true }]}>
              <Select showSearch placeholder="选择客户"
                optionFilterProp="label"
                options={customers.map((c) => ({ value: c.id, label: `${c.customer_code} · ${c.customer_name}` }))} />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item name="resource_id" label="货源" rules={[{ required: true }]}>
              <Select showSearch placeholder="选择货源"
                optionFilterProp="label"
                options={resources.map((r) => ({ value: r.id, label: `${r.resource_code} · ${r.account_name || r.resource_type}` }))} />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={12}>
          <Col span={8}>
            <Form.Item label="数量">
              <InputNumber min={1} value={qty} onChange={(v) => setQty(Number(v) || 1)} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="单位成本">
              <InputNumber min={0} step={0.1} value={cost} onChange={(v) => setCost(Number(v) || 0)} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="单位售价（自动）">
              <InputNumber value={unitPrice} disabled style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>

        <div style={{ background: '#f5f5f5', padding: 16, borderRadius: 8, marginBottom: 12 }}>
          <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }}>
            <Text strong>加价率</Text>
            <Text strong style={{ color: '#0078D4' }}>{markup}%</Text>
          </Space>
          <Slider min={0} max={200} value={markup} onChange={setMarkup}
            marks={{ 0: '0%', 30: '30%', 50: '50%', 100: '100%', 200: '200%' }} />
        </div>

        <Row gutter={12}>
          <Col span={6}>
            <Statistic title="总成本" value={totalCost} precision={2} prefix="¥" />
          </Col>
          <Col span={6}>
            <Statistic title="总售价" value={totalPrice} precision={2} prefix="¥" />
          </Col>
          <Col span={6}>
            <Statistic title="毛利" value={profit} precision={2} prefix="¥"
              valueStyle={{ color: profit >= 0 ? '#107C10' : '#A4262C' }} />
          </Col>
          <Col span={6}>
            <Statistic title="毛利率" value={profitRate} suffix="%"
              valueStyle={{ color: profitRate >= 20 ? '#107C10' : profitRate >= 0 ? '#C19C00' : '#A4262C' }} />
          </Col>
        </Row>
      </Form>
    </Modal>
  );
}

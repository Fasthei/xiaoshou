import { useEffect, useState } from 'react';
import {
  Drawer, Form, InputNumber, Input, Space, Button, Alert, Descriptions, Tag,
  message as antdMessage,
} from 'antd';
import { api } from '../api/axios';

/**
 * BillAdjustmentDrawer — 账单中心覆盖 (客户 × 货源 × 月份)。
 *
 * 业务口径：
 *   默认: 折扣 = 最新 approved allocation.discount_rate
 *   覆盖: 本 drawer 可为该月单独指定 discount_rate_override / surcharge。
 *
 * PUT /api/bills/adjustment  upsert
 * DELETE /api/bills/adjustment  清除覆盖 (还原为订单折扣, 不含 surcharge)
 */
interface Props {
  open: boolean;
  onClose: () => void;
  onSaved?: () => void;

  customer_id: number;
  customer_name: string;
  resource_id: number;
  resource_code: string | null;
  identifier_field: string | null;
  month: string;                              // YYYY-MM

  // 当前行上下文 —— 只读展示
  original_cost: number;
  discount_rate_pct: number;                  // 订单折扣率 %
  discount_override?: number | null;          // 现有覆盖值
  surcharge?: number | null;
  notes?: string | null;
  has_adjustment?: boolean;
}

export default function BillAdjustmentDrawer(props: Props) {
  const {
    open, onClose, onSaved,
    customer_id, customer_name, resource_id, resource_code,
    identifier_field, month,
    original_cost, discount_rate_pct,
    discount_override, surcharge, notes, has_adjustment,
  } = props;

  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    if (!open) return;
    form.setFieldsValue({
      discount_rate_override: discount_override ?? null,
      surcharge: surcharge ?? null,
      notes: notes ?? '',
    });
  }, [open, discount_override, surcharge, notes, form]);

  const previewFinal = (override: number | null, sur: number | null): number => {
    const pct = override != null ? override : discount_rate_pct;
    const s = sur ?? 0;
    return original_cost * (1 - pct / 100) + s;
  };

  const handleSave = async () => {
    try {
      const v = await form.validateFields();
      setSaving(true);
      await api.put('/api/bills/adjustment', {
        customer_id, resource_id, month,
        discount_rate_override: v.discount_rate_override,
        surcharge: v.surcharge,
        notes: v.notes || null,
      });
      antdMessage.success('已保存');
      onSaved?.();
      onClose();
    } catch (e: any) {
      if (e?.errorFields) return;  // antd validation
      antdMessage.error('保存失败: ' + (e?.response?.data?.detail || e?.message || '未知错误'));
    } finally {
      setSaving(false);
    }
  };

  const handleClear = async () => {
    if (!has_adjustment) {
      onClose();
      return;
    }
    setClearing(true);
    try {
      await api.delete('/api/bills/adjustment', {
        params: { customer_id, resource_id, month },
      });
      antdMessage.success('覆盖已清除，恢复订单折扣');
      onSaved?.();
      onClose();
    } catch (e: any) {
      antdMessage.error('清除失败: ' + (e?.response?.data?.detail || e?.message));
    } finally {
      setClearing(false);
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={`编辑账单 — ${customer_name}`}
      width={520}
      destroyOnClose
      footer={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Button
            danger
            disabled={!has_adjustment}
            loading={clearing}
            onClick={handleClear}
          >
            清除覆盖（还原订单折扣）
          </Button>
          <Space>
            <Button onClick={onClose}>取消</Button>
            <Button type="primary" loading={saving} onClick={handleSave}>
              保存
            </Button>
          </Space>
        </Space>
      }
    >
      <Alert
        type="info" showIcon style={{ marginBottom: 16 }}
        message="账单中心按 (客户 × 货源 × 月) 覆盖折扣率 / 附加手续费。"
        description="默认折扣率沿用最新 approved 订单；在此填值可单独覆盖当月。清除后恢复订单折扣。"
      />

      <Descriptions
        size="small" column={1} bordered style={{ marginBottom: 16 }}
      >
        <Descriptions.Item label="月份">{month}</Descriptions.Item>
        <Descriptions.Item label="货源">
          {resource_code ?? '-'}{' '}
          {identifier_field ? <Tag>{identifier_field}</Tag> : null}
        </Descriptions.Item>
        <Descriptions.Item label="原价 (cc_usage)">
          ¥ {original_cost.toFixed(2)}
        </Descriptions.Item>
        <Descriptions.Item label="订单折扣率">
          {discount_rate_pct.toFixed(2)}%
        </Descriptions.Item>
      </Descriptions>

      <Form form={form} layout="vertical">
        <Form.Item
          name="discount_rate_override"
          label="覆盖折扣率 %"
          tooltip="留空=沿用订单折扣；0-100, 可负表加价"
        >
          <InputNumber
            min={-100} max={100} step={0.5} precision={2}
            placeholder="留空 = 沿用订单"
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item
          name="surcharge"
          label="附加手续费 ¥"
          tooltip="可正可负；叠加在折后价之上"
        >
          <InputNumber
            step={10} precision={2}
            placeholder="留空 = 无"
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item name="notes" label="备注">
          <Input.TextArea rows={2} maxLength={500} showCount />
        </Form.Item>

        <Form.Item shouldUpdate noStyle>
          {({ getFieldsValue }) => {
            const { discount_rate_override: ov, surcharge: su } = getFieldsValue();
            const preview = previewFinal(ov ?? null, su ?? null);
            return (
              <Alert
                type="success" showIcon
                message={`预览折后: ¥ ${preview.toFixed(2)}`}
                description={
                  `= 原价 ${original_cost.toFixed(2)} × (1 − ${(ov ?? discount_rate_pct).toFixed(2)}% )`
                  + ` + 手续费 ${(su ?? 0).toFixed(2)}`
                }
              />
            );
          }}
        </Form.Item>
      </Form>
    </Drawer>
  );
}

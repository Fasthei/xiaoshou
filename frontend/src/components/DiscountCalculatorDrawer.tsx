import { useMemo, useState } from 'react';
import {
  Drawer, Form, InputNumber, Space, Statistic, Divider, Button, Typography, Alert,
  message as antdMessage,
} from 'antd';
import { CopyOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * DiscountCalculatorDrawer — 纯前端折扣计算器（账单中心用）。
 *
 * 输入:
 *   - cost     原始成本
 *   - discount 折扣率 0~100 (%)      → 折后金额 = cost × (1 - discount/100)
 *   - markup   加价率 0~任意 (%)     → 加价售价 = cost × (1 + markup/100)
 * 输出:
 *   - discounted_amount  折后金额
 *   - selling_price      加价售价
 *   - gross_profit       毛利 = selling_price - discounted_amount
 *   - gross_profit_rate  毛利率 = gross_profit / selling_price
 */
export default function DiscountCalculatorDrawer({ open, onClose }: Props) {
  const [cost, setCost] = useState<number | null>(1000);
  const [discount, setDiscount] = useState<number | null>(10);
  const [markup, setMarkup] = useState<number | null>(30);

  const calc = useMemo(() => {
    const c = Number(cost) || 0;
    const d = Number(discount) || 0;
    const m = Number(markup) || 0;
    const discounted = c * (1 - d / 100);
    const selling = c * (1 + m / 100);
    const profit = selling - discounted;
    const profitRate = selling > 0 ? profit / selling : 0;
    return { discounted, selling, profit, profitRate };
  }, [cost, discount, markup]);

  const handleCopy = async () => {
    const text = [
      `原始成本: ¥${Number(cost || 0).toFixed(2)}`,
      `折扣率: ${Number(discount || 0).toFixed(2)}%`,
      `加价率: ${Number(markup || 0).toFixed(2)}%`,
      `折后金额: ¥${calc.discounted.toFixed(2)}`,
      `加价售价: ¥${calc.selling.toFixed(2)}`,
      `毛利: ¥${calc.profit.toFixed(2)}`,
      `毛利率: ${(calc.profitRate * 100).toFixed(2)}%`,
    ].join('\n');
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        antdMessage.success('已复制到剪贴板');
      } else {
        // fallback for non-secure contexts
        const ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        antdMessage.success('已复制到剪贴板');
      }
    } catch (e: any) {
      antdMessage.error('复制失败：' + (e?.message || '未知错误'));
    }
  };

  return (
    <Drawer
      title="折扣计算器"
      open={open}
      onClose={onClose}
      placement="right"
      width={480}
      destroyOnClose={false}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="纯本地计算"
        description="不调用后端；输入变化即时刷新结果。"
      />

      <Form layout="vertical">
        <Form.Item
          label="原始成本 (￥)"
          tooltip="采购 / 云管拿到的原始成本"
        >
          <InputNumber
            value={cost}
            onChange={(v) => setCost(v as number | null)}
            min={0}
            step={100}
            precision={2}
            style={{ width: '100%' }}
            addonBefore="¥"
          />
        </Form.Item>

        <Form.Item
          label="折扣率 (%)"
          tooltip="应用在原始成本上的折扣，0~100"
        >
          <InputNumber
            value={discount}
            onChange={(v) => setDiscount(v as number | null)}
            min={0}
            max={100}
            step={1}
            precision={2}
            style={{ width: '100%' }}
            addonAfter="%"
          />
        </Form.Item>

        <Form.Item
          label="加价率 (%)"
          tooltip="应用在原始成本上的加价（markup），反向算售价"
        >
          <InputNumber
            value={markup}
            onChange={(v) => setMarkup(v as number | null)}
            min={0}
            step={5}
            precision={2}
            style={{ width: '100%' }}
            addonAfter="%"
          />
        </Form.Item>
      </Form>

      <Divider>计算结果</Divider>

      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        <Statistic
          title="折后金额（成本 × (1 − 折扣率)）"
          value={calc.discounted}
          precision={2}
          prefix="¥"
          valueStyle={{ color: '#0ea5e9' }}
        />
        <Statistic
          title="加价售价（成本 × (1 + 加价率)）"
          value={calc.selling}
          precision={2}
          prefix="¥"
          valueStyle={{ color: '#4f46e5' }}
        />
        <Statistic
          title="毛利（售价 − 折后金额）"
          value={calc.profit}
          precision={2}
          prefix="¥"
          valueStyle={{ color: calc.profit >= 0 ? '#22c55e' : '#ef4444' }}
        />
        <Statistic
          title="毛利率"
          value={(calc.profitRate * 100).toFixed(2)}
          suffix="%"
          valueStyle={{ color: calc.profitRate >= 0 ? '#22c55e' : '#ef4444' }}
        />

        {calc.selling <= 0 && (
          <Text type="warning">售价为 0，毛利率无意义。</Text>
        )}
      </Space>

      <Divider />

      <Button
        type="primary"
        icon={<CopyOutlined />}
        block
        onClick={handleCopy}
      >
        复制结果到剪贴板
      </Button>
    </Drawer>
  );
}

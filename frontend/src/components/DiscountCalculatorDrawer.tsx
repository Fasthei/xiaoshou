import { useMemo, useState } from 'react';
import {
  Drawer, Form, InputNumber, Input, Space, Statistic, Divider, Button, Typography, Alert,
  Table, Tag,
  message as antdMessage,
} from 'antd';
import { CopyOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';

const { Text } = Typography;

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * 折扣计算器 — 按货源分别计算折扣 + 汇总。
 *
 * 业务规则：同一个客户下的不同货源可以各有不同折扣率与加价率。
 * 所以计算器必须支持「逐行输入 → 按行计算 → 汇总合计」而不是单账总。
 *
 * 每行输入：
 *   - 货源名（可选，便于复制结果识别）
 *   - 原始成本 (cost)
 *   - 折扣率 (%)，应用在成本上：discounted = cost * (1 - d/100)
 *   - 加价率 (%)，反向算售价： selling = cost * (1 + m/100)
 *
 * 每行输出：
 *   - discounted / selling / profit = selling - discounted / profit_rate
 *
 * 汇总（表尾）：
 *   - 合计原始成本 / 合计折后 / 合计售价 / 合计毛利 / 整体毛利率
 */

interface Line {
  id: number;
  name: string;
  cost: number | null;
  discount: number | null;  // %
  markup: number | null;    // %
}

function computeLine(l: Line) {
  const c = Number(l.cost) || 0;
  const d = Number(l.discount) || 0;
  const m = Number(l.markup) || 0;
  const discounted = c * (1 - d / 100);
  const selling = c * (1 + m / 100);
  const profit = selling - discounted;
  const profitRate = selling > 0 ? profit / selling : 0;
  return { discounted, selling, profit, profitRate };
}

let _seq = 0;
const nextId = () => ++_seq;

export default function DiscountCalculatorDrawer({ open, onClose }: Props) {
  const [lines, setLines] = useState<Line[]>([
    { id: nextId(), name: '货源 1', cost: 1000, discount: 10, markup: 30 },
  ]);

  const computed = useMemo(
    () => lines.map((l) => ({ line: l, ...computeLine(l) })),
    [lines],
  );

  const totals = useMemo(() => {
    const totalCost = computed.reduce((s, x) => s + (Number(x.line.cost) || 0), 0);
    const totalDiscounted = computed.reduce((s, x) => s + x.discounted, 0);
    const totalSelling = computed.reduce((s, x) => s + x.selling, 0);
    const totalProfit = computed.reduce((s, x) => s + x.profit, 0);
    const totalProfitRate = totalSelling > 0 ? totalProfit / totalSelling : 0;
    return { totalCost, totalDiscounted, totalSelling, totalProfit, totalProfitRate };
  }, [computed]);

  const addLine = () => {
    setLines((prev) => [
      ...prev,
      { id: nextId(), name: `货源 ${prev.length + 1}`, cost: 0, discount: 0, markup: 0 },
    ]);
  };

  const removeLine = (id: number) => {
    setLines((prev) => (prev.length <= 1 ? prev : prev.filter((l) => l.id !== id)));
  };

  const updateLine = (id: number, patch: Partial<Line>) => {
    setLines((prev) => prev.map((l) => (l.id === id ? { ...l, ...patch } : l)));
  };

  const handleCopy = async () => {
    const lineStr = computed
      .map((x, i) => {
        const name = x.line.name || `货源 ${i + 1}`;
        return (
          `${name}: 原价 ¥${Number(x.line.cost || 0).toFixed(2)} · `
          + `折扣率 ${Number(x.line.discount || 0).toFixed(2)}% · `
          + `加价率 ${Number(x.line.markup || 0).toFixed(2)}% → `
          + `折后价 ¥${x.discounted.toFixed(2)} / 售价 ¥${x.selling.toFixed(2)} / `
          + `毛利 ¥${x.profit.toFixed(2)} (${(x.profitRate * 100).toFixed(2)}%)`
        );
      })
      .join('\n');
    const sumStr = [
      `—— 合计（${lines.length} 个货源）——`,
      `原价合计: ¥${totals.totalCost.toFixed(2)}`,
      `折后价合计: ¥${totals.totalDiscounted.toFixed(2)}`,
      `售价合计: ¥${totals.totalSelling.toFixed(2)}`,
      `毛利合计: ¥${totals.totalProfit.toFixed(2)}`,
      `整体毛利率: ${(totals.totalProfitRate * 100).toFixed(2)}%`,
    ].join('\n');
    const text = `${lineStr}\n\n${sumStr}`;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        antdMessage.success('已复制到剪贴板');
      } else {
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
      title={<Space>折扣计算器 <Tag color="blue">按货源分别计算</Tag></Space>}
      open={open}
      onClose={onClose}
      placement="right"
      width={780}
      destroyOnClose={false}
    >
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="纯本地计算 · 每个货源可填不同的折扣率与加价率"
        description={
          <>
            字段口径与账单中心一致：<b>原价</b>（原始成本） × <b>折扣率</b> → <b>折后价</b>。
            加价率 / 售价 / 毛利 仅用于算"卖给客户的价"，可解释为：
            <code> 毛利 = 售价 − 折后价</code>。
          </>
        }
      />

      <Table<typeof computed[number]>
        rowKey={(x) => x.line.id}
        dataSource={computed}
        pagination={false}
        size="small"
        columns={[
          {
            title: '货源名',
            width: 140,
            render: (_: any, row) => (
              <Input
                value={row.line.name}
                onChange={(e) => updateLine(row.line.id, { name: e.target.value })}
                placeholder="货源名/识别码"
              />
            ),
          },
          {
            title: '原价 (¥)',
            width: 120,
            render: (_: any, row) => (
              <InputNumber
                value={row.line.cost}
                onChange={(v) => updateLine(row.line.id, { cost: v as number | null })}
                min={0}
                step={100}
                precision={2}
                style={{ width: '100%' }}
              />
            ),
          },
          {
            title: '折扣率 (%)',
            width: 110,
            render: (_: any, row) => (
              <InputNumber
                value={row.line.discount}
                onChange={(v) => updateLine(row.line.id, { discount: v as number | null })}
                min={0}
                max={100}
                step={1}
                precision={2}
                style={{ width: '100%' }}
              />
            ),
          },
          {
            title: '加价率 (%)',
            width: 110,
            render: (_: any, row) => (
              <InputNumber
                value={row.line.markup}
                onChange={(v) => updateLine(row.line.id, { markup: v as number | null })}
                min={0}
                step={5}
                precision={2}
                style={{ width: '100%' }}
              />
            ),
          },
          {
            title: '折后价',
            width: 110,
            render: (_: any, row) => (
              <Text style={{ color: '#0ea5e9' }}>¥{row.discounted.toFixed(2)}</Text>
            ),
          },
          {
            title: '售价',
            width: 110,
            render: (_: any, row) => (
              <Text style={{ color: '#4f46e5' }}>¥{row.selling.toFixed(2)}</Text>
            ),
          },
          {
            title: '毛利',
            width: 110,
            render: (_: any, row) => (
              <Text strong style={{ color: row.profit >= 0 ? '#22c55e' : '#ef4444' }}>
                ¥{row.profit.toFixed(2)}
              </Text>
            ),
          },
          {
            title: '毛利率',
            width: 90,
            render: (_: any, row) => `${(row.profitRate * 100).toFixed(2)}%`,
          },
          {
            title: '',
            width: 40,
            render: (_: any, row) => (
              <Button
                size="small"
                type="text"
                danger
                icon={<DeleteOutlined />}
                disabled={lines.length <= 1}
                onClick={() => removeLine(row.line.id)}
              />
            ),
          },
        ]}
      />

      <Button
        type="dashed"
        block
        icon={<PlusOutlined />}
        onClick={addLine}
        style={{ marginTop: 12 }}
      >
        添加一个货源行
      </Button>

      <Divider>汇总（整单口径）</Divider>

      <Space direction="vertical" size={12} style={{ width: '100%' }}>
        <Space wrap size={24}>
          <Statistic
            title="原价合计"
            value={totals.totalCost}
            precision={2}
            prefix="¥"
          />
          <Statistic
            title="折后价合计"
            value={totals.totalDiscounted}
            precision={2}
            prefix="¥"
            valueStyle={{ color: '#0ea5e9' }}
          />
          <Statistic
            title="合计加价售价"
            value={totals.totalSelling}
            precision={2}
            prefix="¥"
            valueStyle={{ color: '#4f46e5' }}
          />
        </Space>
        <Space wrap size={24}>
          <Statistic
            title="合计毛利"
            value={totals.totalProfit}
            precision={2}
            prefix="¥"
            valueStyle={{ color: totals.totalProfit >= 0 ? '#22c55e' : '#ef4444' }}
          />
          <Statistic
            title="整体毛利率"
            value={(totals.totalProfitRate * 100).toFixed(2)}
            suffix="%"
            valueStyle={{ color: totals.totalProfitRate >= 0 ? '#22c55e' : '#ef4444' }}
          />
        </Space>
        {totals.totalSelling <= 0 && (
          <Text type="warning">合计售价为 0，毛利率无意义。</Text>
        )}
      </Space>

      <Divider />

      <Form layout="inline">
        <Form.Item>
          <Button type="primary" icon={<CopyOutlined />} onClick={handleCopy}>
            复制结果到剪贴板
          </Button>
        </Form.Item>
      </Form>
    </Drawer>
  );
}

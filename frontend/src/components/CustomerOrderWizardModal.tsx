import { useEffect, useMemo, useState } from 'react';
import {
  Modal, Steps, Form, Input, Select, Upload, Button, Table, InputNumber, Space, Typography,
  message as antdMessage,
} from 'antd';
import { UploadOutlined, PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';
import { api } from '../api/axios';
import type { Resource } from '../types';

const { Text } = Typography;

/**
 * CustomerOrderWizardModal — 客户 + 订单两步向导。
 *
 *   Step 1: 客户信息（customer_name / customer_type / referrer / customer_status）
 *   Step 2: 订单详情（**折扣明细表格** + 合同上传）
 *
 * Step 2 表格每行 = 一条 allocation line，支持:
 *   货源 · 数量 · 原价 · 折扣率% · 折后单价 · 小计 · 删除
 *   折扣率 ↔ 折后单价 双向联动（编辑任一反算另一）
 *   右下角合计 = Σ 小计
 *
 * 提交走 POST /api/allocations/batch 批量创建明细。
 */

type CustomerType = 'direct' | 'channel';
type CustomerStatus = 'potential' | 'active';

interface Step1Values {
  customer_name: string;
  customer_type: CustomerType;
  referrer?: string;
  customer_status: CustomerStatus;
  channel_notes?: string;
}

interface Step2Values {
  order_note?: string;
  contract_file?: UploadFile | null;
}

interface OrderLine {
  resource_id?: number;
  quantity?: number;
  pre_unit_price?: number;
  discount_rate?: number;
  post_unit_price?: number;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  initialCustomer?: { id: number; customer_name: string; customer_code: string } | null;
}

const round2 = (n: number) => Math.round(n * 100) / 100;

export default function CustomerOrderWizardModal({ open, onClose, onSuccess, initialCustomer }: Props) {
  const startStep = initialCustomer ? 1 : 0;
  const [current, setCurrent] = useState(startStep);
  const [submitting, setSubmitting] = useState(false);
  const [step1Form] = Form.useForm<Step1Values>();
  const [step2Form] = Form.useForm<Step2Values>();
  const [step1Values, setStep1Values] = useState<Step1Values | null>(null);
  const [contractFile, setContractFile] = useState<UploadFile | null>(null);
  const [lines, setLines] = useState<OrderLine[]>([
    { quantity: 1, pre_unit_price: 0, discount_rate: 0, post_unit_price: 0 },
  ]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [resLoading, setResLoading] = useState(false);

  useEffect(() => {
    if (!open) return;
    setResLoading(true);
    api
      .get('/api/resources', { params: { page_size: 100 } })
      .then(({ data }) => setResources(data.items || []))
      .catch(() => antdMessage.error('货源列表加载失败'))
      .finally(() => setResLoading(false));
  }, [open]);

  const resourceOptions = useMemo(
    () =>
      resources.map((r) => ({
        value: r.id,
        label:
          `${r.resource_code} · ${r.account_name ?? '-'}` +
          (r.cloud_provider ? ` (${r.cloud_provider})` : ''),
      })),
    [resources],
  );

  const reset = () => {
    setCurrent(initialCustomer ? 1 : 0);
    setStep1Values(null);
    setContractFile(null);
    setLines([{ quantity: 1, pre_unit_price: 0, discount_rate: 0, post_unit_price: 0 }]);
    step1Form.resetFields();
    step2Form.resetFields();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const updateLine = (idx: number, patch: Partial<OrderLine>) => {
    setLines((prev) => {
      const next = prev.map((l, i) => (i === idx ? { ...l, ...patch } : l));
      const row = next[idx];

      // 折扣率改变 → 反算 post_unit_price
      if ('discount_rate' in patch || 'pre_unit_price' in patch) {
        const pre = Number(row.pre_unit_price ?? 0);
        const rate = Number(row.discount_rate ?? 0);
        row.post_unit_price = round2(pre * (1 - rate / 100));
      }
      // 折后单价改变 → 反算 discount_rate
      if ('post_unit_price' in patch) {
        const pre = Number(row.pre_unit_price ?? 0);
        const post = Number(row.post_unit_price ?? 0);
        if (pre > 0) {
          row.discount_rate = round2((1 - post / pre) * 100);
        }
      }
      return next;
    });
  };

  const addLine = () =>
    setLines((prev) => [
      ...prev,
      { quantity: 1, pre_unit_price: 0, discount_rate: 0, post_unit_price: 0 },
    ]);

  const removeLine = (idx: number) =>
    setLines((prev) => (prev.length <= 1 ? prev : prev.filter((_, i) => i !== idx)));

  const totalAmount = useMemo(
    () =>
      lines.reduce(
        (sum, l) => sum + (Number(l.quantity) || 0) * (Number(l.post_unit_price) || 0),
        0,
      ),
    [lines],
  );

  const handleNext = async () => {
    try {
      const v = await step1Form.validateFields();
      setStep1Values(v);
      setCurrent(1);
    } catch {
      /* antd 已展示字段错误 */
    }
  };

  const handleBack = () => setCurrent(0);

  const validateLines = (): string | null => {
    if (lines.length === 0) return '至少一条明细';
    for (const [i, l] of lines.entries()) {
      if (!l.resource_id) return `第 ${i + 1} 行未选货源`;
      if (!l.quantity || l.quantity <= 0) return `第 ${i + 1} 行数量必须 > 0`;
      if (l.post_unit_price == null || l.post_unit_price < 0) return `第 ${i + 1} 行折后单价无效`;
    }
    return null;
  };

  const handleSubmit = async () => {
    try {
      const orderVals = await step2Form.validateFields();
      const lineErr = validateLines();
      if (lineErr) {
        antdMessage.error(lineErr);
        return;
      }
      if (!contractFile) {
        antdMessage.error('新建订单必须上传合同文件');
        return;
      }
      setSubmitting(true);

      // 1) 若是新客户则先创建客户
      let customerId: number | undefined = initialCustomer?.id;
      if (!customerId && step1Values) {
        const customer_code = 'CUST-' + Math.random().toString(36).slice(2, 10).toUpperCase();
        const { data: created } = await api.post('/api/customers', {
          customer_code,
          ...step1Values,
        });
        customerId = created.id;
      }
      if (!customerId) {
        antdMessage.error('客户信息缺失');
        setSubmitting(false);
        return;
      }

      // 2) 批量创建订单明细
      await api.post('/api/allocations/batch', {
        customer_id: customerId,
        contract_id: null,
        lines: lines.map((l) => ({
          resource_id: l.resource_id,
          quantity: l.quantity,
          unit_cost: l.pre_unit_price,
          unit_price: l.post_unit_price,
          discount_rate: l.discount_rate,
        })),
      });

      // 3) 合同上传接口暂未实现（后端 Task），先保留 file 但 skip 上传
      console.debug('[CustomerOrderWizard] contract pending upload', {
        contractFile,
        note: orderVals.order_note,
      });

      antdMessage.success('订单已创建，等待审批');
      setSubmitting(false);
      onSuccess?.();
      handleClose();
    } catch (e) {
      console.error('[CustomerOrderWizard] submit failed', e);
      setSubmitting(false);
    }
  };

  const columns = [
    {
      title: '货源',
      width: 220,
      render: (_: unknown, r: OrderLine, i: number) => (
        <Select
          showSearch
          loading={resLoading}
          placeholder="选货源"
          value={r.resource_id}
          options={resourceOptions}
          filterOption={(input, opt) =>
            String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
          }
          onChange={(v) => updateLine(i, { resource_id: v })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '数量',
      width: 80,
      render: (_: unknown, r: OrderLine, i: number) => (
        <InputNumber
          min={1}
          value={r.quantity}
          onChange={(v) => updateLine(i, { quantity: v ?? 1 })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '原价 ¥',
      width: 110,
      render: (_: unknown, r: OrderLine, i: number) => (
        <InputNumber
          min={0}
          step={0.01}
          value={r.pre_unit_price}
          onChange={(v) => updateLine(i, { pre_unit_price: v ?? 0 })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '折扣率 %',
      width: 100,
      render: (_: unknown, r: OrderLine, i: number) => (
        <InputNumber
          min={-100}
          max={100}
          step={0.1}
          value={r.discount_rate}
          onChange={(v) => updateLine(i, { discount_rate: v ?? 0 })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '折后单价 ¥',
      width: 120,
      render: (_: unknown, r: OrderLine, i: number) => (
        <InputNumber
          min={0}
          step={0.01}
          value={r.post_unit_price}
          onChange={(v) => updateLine(i, { post_unit_price: v ?? 0 })}
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '小计',
      width: 100,
      render: (_: unknown, r: OrderLine) =>
        ((Number(r.quantity) || 0) * (Number(r.post_unit_price) || 0)).toFixed(2),
    },
    {
      title: '',
      width: 48,
      render: (_: unknown, __: OrderLine, i: number) => (
        <Button
          danger
          type="text"
          icon={<DeleteOutlined />}
          onClick={() => removeLine(i)}
          disabled={lines.length <= 1}
        />
      ),
    },
  ];

  return (
    <Modal
      open={open}
      title={initialCustomer ? `新建订单 — ${initialCustomer.customer_name}` : '新建客户 + 新建订单'}
      onCancel={handleClose}
      width={900}
      destroyOnClose
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button onClick={handleClose}>取消</Button>
          <div>
            {current > 0 && !initialCustomer && (
              <Button style={{ marginRight: 8 }} onClick={handleBack} disabled={submitting}>
                上一步
              </Button>
            )}
            {current === 0 && (
              <Button type="primary" onClick={handleNext}>
                下一步
              </Button>
            )}
            {current === 1 && (
              <Button type="primary" loading={submitting} onClick={handleSubmit}>
                提交（待审批）
              </Button>
            )}
          </div>
        </div>
      }
    >
      {!initialCustomer && (
        <Steps
          current={current}
          items={[{ title: '客户信息' }, { title: '订单详情（含合同）' }]}
          style={{ marginBottom: 24 }}
        />
      )}

      {/* Step 1: 客户信息 */}
      <div style={{ display: current === 0 ? 'block' : 'none' }}>
        <Form<Step1Values>
          form={step1Form}
          layout="vertical"
          initialValues={{ customer_type: 'direct', customer_status: 'potential' }}
        >
          <Form.Item name="customer_name" label="客户名称" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="customer_type"
            label="客户类型"
            rules={[{ required: true }]}
            tooltip="直客 = 我们直接服务；渠道 = 我们服务渠道商，终端用户模糊"
          >
            <Select
              options={[
                { value: 'direct', label: '直客' },
                { value: 'channel', label: '渠道客户' },
              ]}
            />
          </Form.Item>
          <Form.Item shouldUpdate={(prev, cur) => prev.customer_type !== cur.customer_type} noStyle>
            {({ getFieldValue }) =>
              getFieldValue('customer_type') === 'channel' ? (
                <Form.Item
                  name="channel_notes"
                  label="渠道备注"
                  tooltip="渠道方告诉我们的终端用户说明（可空）"
                >
                  <Input.TextArea rows={2} placeholder="如: 终端为 XX 省 YY 集团旗下子公司" />
                </Form.Item>
              ) : null
            }
          </Form.Item>
          <Form.Item name="referrer" label="转介绍来源" tooltip="谁把这个客户转介绍过来的（可空）">
            <Input placeholder="如: 老客户 XXX 转介绍 / 合作伙伴 YYY 推荐" maxLength={100} />
          </Form.Item>
          <Form.Item name="customer_status" label="初始状态" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'potential', label: '潜在客户' },
                { value: 'active', label: '客户池' },
              ]}
            />
          </Form.Item>
        </Form>
      </div>

      {/* Step 2: 订单详情 — 折扣明细表格 */}
      <div style={{ display: current === 1 ? 'block' : 'none' }}>
        <Form<Step2Values> form={step2Form} layout="vertical">
          <Form.Item label="订单明细" required>
            <Table<OrderLine>
              dataSource={lines.map((l, i) => ({ ...l, __key: i })) as any}
              rowKey={(_, i) => String(i)}
              columns={columns as any}
              pagination={false}
              size="small"
              footer={() => (
                <Space style={{ justifyContent: 'space-between', width: '100%', display: 'flex' }}>
                  <Button icon={<PlusOutlined />} onClick={addLine}>
                    添加明细行
                  </Button>
                  <Text strong>合计 ¥ {totalAmount.toFixed(2)}</Text>
                </Space>
              )}
            />
          </Form.Item>

          <Form.Item name="order_note" label="订单备注">
            <Input.TextArea rows={3} placeholder="订单说明、特殊条款等" />
          </Form.Item>

          <Form.Item
            label="合同文件"
            required
            tooltip="新建订单必须上传合同（PDF / Word / 图片）"
            extra="支持 .pdf / .doc / .docx / .jpg / .png；合同将落到 Azure Blob，同时挂到该客户的合同列表下"
          >
            <Upload
              accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
              maxCount={1}
              beforeUpload={(file) => {
                setContractFile({
                  uid: String(Date.now()),
                  name: file.name,
                  status: 'done',
                  originFileObj: file as any,
                });
                return false;
              }}
              onRemove={() => {
                setContractFile(null);
                return true;
              }}
              fileList={contractFile ? [contractFile] : []}
            >
              <Button icon={<UploadOutlined />}>选择合同文件</Button>
            </Upload>
          </Form.Item>

          <div
            style={{
              marginTop: 8,
              padding: 12,
              background: '#fff7e6',
              borderRadius: 6,
              color: '#8a6100',
              fontSize: 12,
            }}
          >
            提交后订单状态默认为 <b>待审批 (pending)</b>，需销售主管审批后方可生效。
          </div>
        </Form>
      </div>
    </Modal>
  );
}

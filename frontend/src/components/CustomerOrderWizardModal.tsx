import { useState } from 'react';
import {
  Modal, Steps, Form, Input, Select, Upload, Button, message as antdMessage,
} from 'antd';
import { UploadOutlined } from '@ant-design/icons';
import type { UploadFile } from 'antd/es/upload/interface';

/**
 * CustomerOrderWizardModal — skeleton.
 *
 * 两步向导：
 *   Step 1: 客户信息（customer_code / customer_name / customer_type / referrer / customer_status）
 *   Step 2: 订单详情（多货源选择器 + 合同上传 — 多货源选择器占位，等后端 Task #3/#4 完成）
 *
 * 提交目前是 stub，显示 "pending backend" 提示。实际接线等下列后端 API 就位：
 *   - POST /api/customers                             (已存在)
 *   - POST /api/orders （订单 + 多货源 + 合同上传）  (待实现, 对应后端 Task #3/#4)
 *   - 合同文件上传 Azure Blob                           (待实现, 对应后端 Task)
 */

type CustomerType = 'direct' | 'channel';
type CustomerStatus = 'potential' | 'active';

interface Step1Values {
  customer_code: string;
  customer_name: string;
  customer_type: CustomerType;
  referrer?: string;
  customer_status: CustomerStatus;
  channel_notes?: string;
}

interface Step2Values {
  order_note?: string;
  // 多货源行：placeholder，等 multi-resource selector 组件就位再换
  resource_lines?: Array<{ resource_id?: number; end_user_label?: string }>;
  contract_file?: UploadFile | null;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export default function CustomerOrderWizardModal({ open, onClose, onSuccess }: Props) {
  const [current, setCurrent] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [step1Form] = Form.useForm<Step1Values>();
  const [step2Form] = Form.useForm<Step2Values>();
  const [step1Values, setStep1Values] = useState<Step1Values | null>(null);
  const [contractFile, setContractFile] = useState<UploadFile | null>(null);

  const reset = () => {
    setCurrent(0);
    setStep1Values(null);
    setContractFile(null);
    step1Form.resetFields();
    step2Form.resetFields();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  const handleNext = async () => {
    try {
      const v = await step1Form.validateFields();
      setStep1Values(v);
      setCurrent(1);
    } catch {
      // antd 已展示字段错误
    }
  };

  const handleBack = () => setCurrent(0);

  const handleSubmit = async () => {
    try {
      const orderVals = await step2Form.validateFields();
      if (!contractFile) {
        antdMessage.error('新建订单必须上传合同文件');
        return;
      }
      setSubmitting(true);
      // TODO: 后端 Task #3 (POST /api/orders with multi-resource) + Task #4 (Azure Blob 合同上传) 就位后接线
      // 伪代码:
      //   1) const customer = await api.post('/api/customers', step1Values)
      //   2) const formData = new FormData()
      //      formData.append('customer_id', customer.id)
      //      formData.append('note', orderVals.order_note || '')
      //      formData.append('resources', JSON.stringify(orderVals.resource_lines || []))
      //      formData.append('contract', contractFile.originFileObj)
      //   3) await api.post('/api/orders', formData, { headers: { 'Content-Type': 'multipart/form-data' }})
      //   4) 订单 approval_status 默认 'pending'，等销售主管审批
      console.debug('[CustomerOrderWizard] stub submit', { step1Values, orderVals, contractFile });
      antdMessage.info('pending backend — 客户 + 订单一步创建接口待实现（Task #3 / #4）');
      setSubmitting(false);
      onSuccess?.();
      handleClose();
    } catch {
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open}
      title="新建客户 + 新建订单"
      onCancel={handleClose}
      width={720}
      destroyOnClose
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <Button onClick={handleClose}>取消</Button>
          <div>
            {current > 0 && (
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
      <Steps
        current={current}
        items={[
          { title: '客户信息' },
          { title: '订单详情（含合同）' },
        ]}
        style={{ marginBottom: 24 }}
      />

      {/* Step 1: 客户信息 */}
      <div style={{ display: current === 0 ? 'block' : 'none' }}>
        <Form<Step1Values>
          form={step1Form}
          layout="vertical"
          initialValues={{ customer_type: 'direct', customer_status: 'potential' }}
        >
          <Form.Item name="customer_code" label="客户编号" rules={[{ required: true }]}>
            <Input placeholder="如: CUST-2026-001" />
          </Form.Item>
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
          <Form.Item
            shouldUpdate={(prev, cur) => prev.customer_type !== cur.customer_type}
            noStyle
          >
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
          <Form.Item
            name="referrer"
            label="转介绍来源"
            tooltip="谁把这个客户转介绍过来的（可空）"
          >
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

      {/* Step 2: 订单详情 */}
      <div style={{ display: current === 1 ? 'block' : 'none' }}>
        <Form<Step2Values> form={step2Form} layout="vertical">
          {/* TODO: 替换为 OrderCreateMultiResourceModal 的多货源选择器组件
              （等后端 Task #3 提供 order + multi-resource 接口 + 前端 multi-resource selector 组件就位）
              每行形如: { resource_id, end_user_label? } */}
          <Form.Item label="多货源选择（占位）">
            <div
              style={{
                border: '1px dashed #d9d9d9',
                borderRadius: 8,
                padding: 16,
                background: '#fafafa',
                color: '#94a3b8',
                fontSize: 13,
              }}
            >
              多货源选择器待接入 — 等后端 POST /api/orders (multi-resource) 和
              OrderCreateMultiResourceModal 组件就位。每行货源支持选填 end_user_label
              （渠道客户用）。
            </div>
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
                return false; // prevent auto upload, handled on submit
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

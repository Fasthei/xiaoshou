import { Button, Card, Typography, Space, Tag } from 'antd';
import { LoginOutlined, ThunderboltFilled, SafetyCertificateOutlined } from '@ant-design/icons';
import { authorizeUrl, randomState } from '../config/casdoor';
import '../styles/aurora.css';

const { Title, Paragraph, Text } = Typography;

export default function Login() {
  const handleLogin = () => {
    const state = randomState();
    sessionStorage.setItem('casdoor_state', state);
    window.location.href = authorizeUrl(state);
  };

  return (
    <>
      <div style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
        background: '#F5F7FA',
      }}>
        <Card
          className="page-fade"
          styles={{ body: { padding: 32 } }}
          style={{
            width: 440,
            borderRadius: 6,
            background: '#FFFFFF',
            border: '1px solid #E1DFDD',
          }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%', textAlign: 'center' }}>
            <div style={{
              width: 72, height: 72, margin: '0 auto',
              borderRadius: 6,
              background: '#0078D4',
              display: 'grid', placeItems: 'center',
              fontSize: 36,
            }}>
              🛒
            </div>
            <div>
              <Title level={2} style={{ color: '#1F2937', margin: 0, letterSpacing: 1 }}>
                销售系统
              </Title>
              <Text style={{ color: '#6B7280', letterSpacing: 6 }}>
                XIAOSHOU · SALES
              </Text>
            </div>
            <Paragraph style={{ color: '#6B7280', marginBottom: 0 }}>
              客户 · 货源 · 订单 · 用量 · 智能洞察
            </Paragraph>
            <Button
              type="primary" size="large" icon={<LoginOutlined />} block
              onClick={handleLogin}
              style={{ height: 44, fontSize: 14, letterSpacing: 1 }}
            >
              使用 Casdoor 统一身份登录
            </Button>
            <Space size={6} wrap style={{ justifyContent: 'center' }}>
              <Tag icon={<ThunderboltFilled />} color="blue">SSO 单点</Tag>
              <Tag icon={<SafetyCertificateOutlined />}>RS256 JWT</Tag>
              <Tag>工单 / 运营 / 云管共用</Tag>
            </Space>
          </Space>
        </Card>
      </div>
    </>
  );
}

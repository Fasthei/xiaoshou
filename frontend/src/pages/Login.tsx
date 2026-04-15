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
      <div className="aurora" />
      <div style={{
        minHeight: '100vh',
        display: 'grid',
        placeItems: 'center',
        padding: 24,
      }}>
        <Card
          className="glass page-fade"
          styles={{ body: { padding: 32 } }}
          style={{
            width: 440,
            borderRadius: 24,
            background: 'rgba(14, 15, 32, 0.55)',
            borderColor: 'rgba(255,255,255,0.18)',
            boxShadow: '0 30px 80px rgba(0,0,0,0.35)',
          }}
        >
          <Space direction="vertical" size="large" style={{ width: '100%', textAlign: 'center' }}>
            <div style={{
              width: 88, height: 88, margin: '0 auto',
              borderRadius: 24,
              background: 'linear-gradient(135deg, #4f46e5 0%, #ec4899 50%, #0ea5e9 100%)',
              display: 'grid', placeItems: 'center',
              fontSize: 44,
              boxShadow: '0 0 60px rgba(79, 70, 229, 0.55)',
            }}>
              🛒
            </div>
            <div>
              <Title level={2} style={{ color: '#fff', margin: 0, letterSpacing: 1 }}>
                销售系统
              </Title>
              <Text style={{ color: 'rgba(255,255,255,0.6)', letterSpacing: 6 }}>
                XIAOSHOU · SALES
              </Text>
            </div>
            <Paragraph style={{ color: 'rgba(255,255,255,0.7)', marginBottom: 0 }}>
              客户 · 货源 · 分配 · 用量 · 智能洞察
            </Paragraph>
            <Button
              type="primary" size="large" icon={<LoginOutlined />} block
              onClick={handleLogin}
              style={{
                height: 48, fontSize: 15, letterSpacing: 1,
                background: 'linear-gradient(90deg, #4f46e5 0%, #ec4899 100%)',
                border: 'none',
                boxShadow: '0 8px 24px rgba(79,70,229,0.45)',
              }}
            >
              使用 Casdoor 统一身份登录
            </Button>
            <Space size={6} wrap style={{ justifyContent: 'center' }}>
              <Tag icon={<ThunderboltFilled />} color="blue">SSO 单点</Tag>
              <Tag icon={<SafetyCertificateOutlined />} color="purple">RS256 JWT</Tag>
              <Tag color="cyan">工单 / 运营 / 云管共用</Tag>
            </Space>
          </Space>
        </Card>
      </div>
    </>
  );
}

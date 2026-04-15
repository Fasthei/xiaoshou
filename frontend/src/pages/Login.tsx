import { Button, Card, Typography, Space } from 'antd';
import { LoginOutlined } from '@ant-design/icons';
import { authorizeUrl, randomState } from '../config/casdoor';

const { Title, Paragraph, Text } = Typography;

export default function Login() {
  const handleLogin = () => {
    const state = randomState();
    sessionStorage.setItem('casdoor_state', state);
    window.location.href = authorizeUrl(state);
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'grid',
      placeItems: 'center',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
    }}>
      <Card style={{ width: 420, boxShadow: '0 24px 60px rgba(0,0,0,0.25)' }}>
        <Space direction="vertical" size="large" style={{ width: '100%', textAlign: 'center' }}>
          <div style={{ fontSize: 56 }}>🛒</div>
          <Title level={2} style={{ margin: 0 }}>销售系统</Title>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            客户 · 货源 · 分配 · 用量
            <br />
            使用统一身份（Casdoor）登录
          </Paragraph>
          <Button type="primary" size="large" icon={<LoginOutlined />} block onClick={handleLogin}>
            使用 Casdoor 登录
          </Button>
          <Text type="secondary" style={{ fontSize: 12 }}>
            🔒 跨系统 SSO：销售 / 工单 / 运营中心 / 云管 共用账号
          </Text>
        </Space>
      </Card>
    </div>
  );
}

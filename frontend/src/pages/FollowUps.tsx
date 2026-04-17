import { Card, Typography, Space, Alert, Button, Empty } from 'antd';
import { TeamOutlined, ScheduleOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';

const { Title, Paragraph, Text } = Typography;

export default function FollowUps() {
  return (
    <div className="page-fade">
      <Card
        bordered={false}
        style={{
          borderRadius: 12, marginBottom: 16,
          background: 'linear-gradient(120deg, #0ea5e9 0%, #6366f1 100%)',
          color: 'white',
        }}
        styles={{ body: { padding: 24 } }}
      >
        <Space direction="vertical" size={4}>
          <Text style={{ color: 'rgba(255,255,255,0.8)', letterSpacing: 4 }}>SALES · 跟进</Text>
          <Title level={2} style={{ color: 'white', margin: 0 }}>
            <ScheduleOutlined /> 客户跟进
          </Title>
          <Paragraph style={{ color: 'rgba(255,255,255,0.85)', marginBottom: 0 }}>
            跟进记录挂在每个客户下 —— 在客户详情抽屉的「跟进」Tab 里查看和新增
          </Paragraph>
        </Space>
      </Card>

      <Card bordered={false} style={{ borderRadius: 12 }}>
        <Alert
          type="info" showIcon
          style={{ marginBottom: 16 }}
          message="暂无全局跟进列表"
          description="目前跟进记录按客户维度存储。请到客户管理里选中客户，打开详情抽屉的「跟进」Tab 查看该客户的跟进时间线。全局跟进列表（聚合所有客户最近跟进）待后端 /api/follow-ups 端点开通后上线。"
        />
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="按客户查看跟进"
        >
          <Link to="/customers">
            <Button type="primary" icon={<TeamOutlined />}>去客户管理</Button>
          </Link>
        </Empty>
      </Card>
    </div>
  );
}

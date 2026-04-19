import { useEffect, useState } from 'react';
import { Card, Space, Tag, Typography, Spin, Empty, Button } from 'antd';
import { BulbFilled, RightOutlined } from '@ant-design/icons';
import { Link } from 'react-router-dom';
import { api } from '../api/axios';

const { Text } = Typography;

interface Item {
  kind: string;
  severity: 'info' | 'warn' | 'crit';
  title: string;
  detail?: string;
}

const SEV_COLOR: Record<string, string> = {
  crit: '#A4262C', warn: '#C19C00', info: '#0078D4',
};

export default function BriefingBanner() {
  const [items, setItems] = useState<Item[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get('/api/briefing')
      .then(({ data }) => setItems(data.items || []))
      .finally(() => setLoading(false));
  }, []);

  return (
    <Card
      bordered={false}
      style={{
        borderRadius: 4,
        background: '#FFFFFF',
        border: '1px solid #E1DFDD',
        color: '#1F2937',
        marginBottom: 16,
      }}
      styles={{ body: { padding: 16 } }}
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <BulbFilled style={{ color: '#C19C00', fontSize: 18 }} />
            <Text strong style={{ color: '#1F2937', fontSize: 15, letterSpacing: 1 }}>
              今日 BRIEFING
            </Text>
          </Space>
          <Link to="/alerts"><Button size="small" type="link">查看全部预警 <RightOutlined /></Button></Link>
        </Space>

        {loading ? <Spin /> :
         items.length === 0 ? <Text type="secondary">一切正常</Text> :
         items.slice(0, 5).map((it, i) => (
           <Space key={i} align="start" style={{ width: '100%' }}>
             <span style={{
               width: 8, height: 8, borderRadius: '50%',
               background: SEV_COLOR[it.severity], marginTop: 7,
             }} />
             <div>
               <Text strong style={{ color: '#1F2937' }}>{it.title}</Text>
               {it.detail ? (
                 <div><Text type="secondary" style={{ fontSize: 12 }}>{it.detail}</Text></div>
               ) : null}
             </div>
             <Tag color={it.severity === 'crit' ? 'red' : it.severity === 'warn' ? 'orange' : 'blue'}>
               {it.kind}
             </Tag>
           </Space>
         ))
        }
      </Space>
    </Card>
  );
}

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
  crit: '#ef4444', warn: '#f59e0b', info: '#4f46e5',
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
        borderRadius: 12,
        background: 'linear-gradient(135deg, #1e1b4b 0%, #4f46e5 80%)',
        color: 'white', marginBottom: 16,
      }}
      styles={{ body: { padding: 20 } }}
    >
      <Space direction="vertical" size={10} style={{ width: '100%' }}>
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <BulbFilled style={{ color: '#fde68a', fontSize: 20 }} />
            <Text strong style={{ color: 'white', fontSize: 16, letterSpacing: 1 }}>
              今日 BRIEFING
            </Text>
          </Space>
          <Link to="/alerts"><Button size="small" ghost>查看全部预警 <RightOutlined /></Button></Link>
        </Space>

        {loading ? <Spin /> :
         items.length === 0 ? <Text style={{ color: 'rgba(255,255,255,0.7)' }}>一切正常 ✨</Text> :
         items.slice(0, 5).map((it, i) => (
           <Space key={i} align="start" style={{ width: '100%' }}>
             <span style={{
               width: 10, height: 10, borderRadius: '50%',
               background: SEV_COLOR[it.severity], marginTop: 6,
               boxShadow: `0 0 8px ${SEV_COLOR[it.severity]}`,
             }} />
             <div>
               <Text strong style={{ color: 'white' }}>{it.title}</Text>
               {it.detail ? (
                 <div><Text style={{ color: 'rgba(255,255,255,0.75)', fontSize: 12 }}>{it.detail}</Text></div>
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

import { useEffect, useState } from 'react';
import { Space, Tabs } from 'antd';
import { BarChartOutlined, TeamOutlined, AuditOutlined } from '@ant-design/icons';
import { useLocation, useNavigate } from 'react-router-dom';
import SalesTeam from './SalesTeam';
import ManagerApprovals from './ManagerApprovals';
import Reports from './Reports';

const VALID_TABS = new Set(['team', 'approvals', 'reports']);

export default function ManagerDashboard() {
  const loc = useLocation();
  const nav = useNavigate();

  // 支持 ?tab=team|approvals|reports 深链
  const params = new URLSearchParams(loc.search);
  const initialTab = VALID_TABS.has(params.get('tab') || '')
    ? (params.get('tab') as string)
    : 'team';
  const [activeKey, setActiveKey] = useState(initialTab);

  useEffect(() => {
    const p = new URLSearchParams(loc.search);
    const t = p.get('tab') || '';
    setActiveKey(VALID_TABS.has(t) ? t : 'team');
  }, [loc.search]);

  const handleTabChange = (key: string) => {
    setActiveKey(key);
    nav(`/manager?tab=${key}`, { replace: true });
  };

  return (
    <div className="page-fade">
      <Tabs
        activeKey={activeKey}
        onChange={handleTabChange}
        items={[
          {
            key: 'team',
            label: <Space size={6}><TeamOutlined />销售团队</Space>,
            children: <SalesTeam />,
          },
          {
            key: 'approvals',
            label: <Space size={6}><AuditOutlined />审批中心</Space>,
            children: <ManagerApprovals />,
          },
          {
            key: 'reports',
            label: <Space size={6}><BarChartOutlined />报表 BI</Space>,
            children: <Reports embedded />,
          },
        ]}
      />
    </div>
  );
}

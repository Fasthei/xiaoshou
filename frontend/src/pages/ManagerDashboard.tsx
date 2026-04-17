import { useEffect, useState } from 'react';
import { Tabs } from 'antd';
import { useLocation, useNavigate } from 'react-router-dom';
import SalesTeam from './SalesTeam';
import ManagerApprovals from './ManagerApprovals';

export default function ManagerDashboard() {
  const loc = useLocation();
  const nav = useNavigate();

  // Support ?tab=approvals for direct URL navigation
  const params = new URLSearchParams(loc.search);
  const initialTab = params.get('tab') === 'approvals' ? 'approvals' : 'team';
  const [activeKey, setActiveKey] = useState(initialTab);

  useEffect(() => {
    const p = new URLSearchParams(loc.search);
    const t = p.get('tab') === 'approvals' ? 'approvals' : 'team';
    setActiveKey(t);
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
          { key: 'team', label: '销售团队', children: <SalesTeam /> },
          { key: 'approvals', label: '审批中心', children: <ManagerApprovals /> },
        ]}
      />
    </div>
  );
}

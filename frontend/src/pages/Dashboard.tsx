import { Navigate } from 'react-router-dom';
import { getCurrentRoles } from '../api/axios';
import ManagerPanorama from '../components/ManagerPanorama';

export default function Dashboard() {
  const roles = getCurrentRoles();
  const isAdmin = roles.includes('admin') || roles.includes('root');
  const isManager = roles.includes('sales-manager');

  // sales-manager (non-admin) sees the panorama
  if (isManager && !isAdmin) return <ManagerPanorama />;

  // plain sales: should never land here (menu hides /dashboard),
  // but redirect defensively to their home
  if (roles.includes('sales') && !isAdmin) return <Navigate to="/home" replace />;

  // admin / root: show panorama as a sensible default
  return <ManagerPanorama />;
}

import { Navigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import { ReactNode } from 'react';
import { useAuth } from '../contexts/AuthContext';

export default function PrivateRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, ready } = useAuth();
  const loc = useLocation();
  if (!ready) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return <>{children}</>;
}

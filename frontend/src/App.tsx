import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { ConfigProvider, theme } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import { ThemeModeProvider, useThemeMode } from './contexts/ThemeContext';
import PrivateRoute from './components/PrivateRoute';
import RoleGuard from './components/RoleGuard';
import AppLayout from './components/AppLayout';
import Login from './pages/Login';
import AuthCallback from './pages/AuthCallback';
import Dashboard from './pages/Dashboard';
import Customers from './pages/Customers';
import Resources from './pages/Resources';
import Allocations from './pages/Allocations';
import Alerts from './pages/Alerts';
import Bills from './pages/Bills';
import SalesTeam from './pages/SalesTeam';
import ManagerDashboard from './pages/ManagerDashboard';
import ManagerApprovals from './pages/ManagerApprovals';
import SalesHome from './pages/SalesHome';
import FollowUps from './pages/FollowUps';

function Shell() {
  const { mode } = useThemeMode();
  return (
    <ConfigProvider
      locale={zhCN}
      theme={{
        algorithm: mode === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
        token: { colorPrimary: '#4f46e5', borderRadius: 8 },
      }}
    >
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/auth/callback" element={<AuthCallback />} />
            <Route element={<PrivateRoute><AppLayout /></PrivateRoute>}>
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route path="/home" element={<SalesHome />} />
              <Route path="/sales/home" element={<SalesHome />} />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/customers" element={<Customers />} />
              <Route path="/follow-ups" element={<FollowUps />} />
              <Route path="/resources" element={<Resources />} />
              <Route path="/allocations" element={<Allocations />} />
              <Route path="/usage" element={<Navigate to="/bills" replace />} />
              <Route path="/alerts" element={<Alerts />} />
              <Route
                path="/bills"
                element={
                  <RoleGuard allowed={['ops', 'sales-manager']}>
                    <Bills />
                  </RoleGuard>
                }
              />
              <Route path="/sales-team" element={<SalesTeam />} />
              <Route
                path="/manager"
                element={
                  <RoleGuard allowed={['sales-manager']}>
                    <ManagerDashboard />
                  </RoleGuard>
                }
              />
              <Route
                path="/manager/approvals"
                element={
                  <RoleGuard allowed={['sales-manager']}>
                    <ManagerApprovals />
                  </RoleGuard>
                }
              />
            </Route>
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ConfigProvider>
  );
}

export default function App() {
  return (
    <ThemeModeProvider>
      <Shell />
    </ThemeModeProvider>
  );
}

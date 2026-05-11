import React from 'react';
import { Navigate, Outlet } from 'react-router-dom';

import { useAuth, type UserRole } from './AuthContext';

export function ProtectedRoute({
  allowedRoles,
  redirectTo = '/login',
}: {
  allowedRoles?: UserRole[];
  redirectTo?: string;
}): React.ReactElement {
  const { isAuthenticated, user } = useAuth();

  if (!isAuthenticated || !user) {
    return <Navigate to={redirectTo} replace />;
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/no-access" replace />;
  }

  return <Outlet />;
}


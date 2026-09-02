import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

import type { ReactElement } from 'react';

export default function PrivateRoute({ children }: { children: ReactElement }) {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  // Pass the page the user was actually trying to reach along as state, so
  // Login.tsx can send them back there after a successful sign-in instead
  // of always landing on a fixed page regardless of what was clicked.
  return isAuthenticated ? children : <Navigate to="/login" state={{ from: location }} replace />;
}

import React, { createContext, useCallback, useContext, useMemo, useState } from 'react';

import { clearTokens, getAccessToken, loginRequest, setTokens } from '../api';
import { decodeJwtPayload } from './jwt';

export type UserRole = 'admin' | 'employee';

export type AuthUser = {
  id: number;
  username: string;
  role: UserRole;
};

type AuthContextValue = {
  user: AuthUser | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function userFromAccessToken(accessToken: string): AuthUser | null {
  const payload = decodeJwtPayload(accessToken);
  if (!payload) {
    return null;
  }
  const id = Number(payload.user_id);
  const username = String(payload.username ?? '');
  const role = String(payload.role ?? '') as UserRole;
  if (!Number.isFinite(id) || !username || (role !== 'admin' && role !== 'employee')) {
    return null;
  }
  return { id, username, role };
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.ReactElement {
  const [user, setUser] = useState<AuthUser | null>(() => {
    const token = getAccessToken();
    return token ? userFromAccessToken(token) : null;
  });

  const login = useCallback(async (username: string, password: string): Promise<void> => {
    const pair = await loginRequest(username, password);
    setTokens(pair.access, pair.refresh);
    const nextUser = userFromAccessToken(pair.access);
    if (!nextUser) {
      clearTokens();
      throw new Error('Не удалось прочитать пользователя из токена.');
    }
    setUser(nextUser);
  }, []);

  const logout = useCallback((): void => {
    clearTokens();
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, isAuthenticated: Boolean(user), login, logout }),
    [login, logout, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth должен использоваться внутри AuthProvider');
  }
  return ctx;
}


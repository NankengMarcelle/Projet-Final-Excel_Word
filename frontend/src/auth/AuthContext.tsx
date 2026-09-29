import { createContext, useCallback, useEffect, useState, type ReactNode } from "react";
import * as authApi from "../api/auth";
import { clearTokens, getRefreshToken, getToken, setTokens } from "../api/client";
import type { UserRead } from "../types/auth";

interface AuthContextValue {
  user: UserRead | null;
  isLoading: boolean;
  login: (email: string, password: string, remember?: boolean) => Promise<void>;
  register: (email: string, password: string, fullName?: string) => Promise<void>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRead | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const loadCurrentUser = useCallback(async () => {
    if (!getToken()) {
      setUser(null);
      setIsLoading(false);
      return;
    }
    try {
      const currentUser = await authApi.getCurrentUser();
      setUser(currentUser);
    } catch {
      clearTokens();
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadCurrentUser();
  }, [loadCurrentUser]);

  const login = useCallback(async (email: string, password: string, remember: boolean = true) => {
    const token = await authApi.login(email, password);
    setTokens(token.access_token, token.refresh_token, remember);
    const currentUser = await authApi.getCurrentUser();
    setUser(currentUser);
  }, []);

  const register = useCallback(async (email: string, password: string, fullName?: string) => {
    await authApi.register({ email, password, full_name: fullName ?? null });
    await login(email, password);
  }, [login]);

  const logout = useCallback(() => {
    // Best-effort, fire-and-forget: the refresh token is revoked server-side so it can't be
    // replayed after logout, but the user shouldn't wait on a network round trip to be signed
    // out locally — clearing local state below is what actually ends their session here.
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      authApi.logout(refreshToken).catch(() => {});
    }
    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

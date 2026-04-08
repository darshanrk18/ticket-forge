"use client";

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import {
  getCurrentUser,
  logout as logoutRequest,
  refreshSession,
  type UserResponse,
} from "@/lib/api";

type AuthState = {
  user: UserResponse | null;
  accessToken: string | null;
};

type AuthContextValue = {
  user: UserResponse | null;
  token: string | null;
  isLoading: boolean;
  setAuth: (user: UserResponse, accessToken: string) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);


export function AuthProvider({ children }: { children: ReactNode }) {
  const [auth, setAuthState] = useState<AuthState>({
    user: null,
    accessToken: null,
  });
  const [isLoading, setIsLoading] = useState(true);
  const didRestoreSession = useRef(false);

  function setAuth(user: UserResponse, accessToken: string) {
    setAuthState({ user, accessToken });
    setIsLoading(false);
  }

  function logout() {
    const token = auth.accessToken;
    setAuthState({ user: null, accessToken: null });
    setIsLoading(false);

    if (!token) {
      return;
    }

    void logoutRequest(token);
  }

  useEffect(() => {
    if (didRestoreSession.current) {
      return;
    }
    didRestoreSession.current = true;

    let isCancelled = false;

    async function restoreSession() {
      const refreshed = await refreshSession();
      if (isCancelled || refreshed.error || !refreshed.data) {
        if (!isCancelled) {
          setAuthState({ user: null, accessToken: null });
          setIsLoading(false);
        }
        return;
      }

      const accessToken = refreshed.data.access_token;
      const currentUser = await getCurrentUser(accessToken);
      if (isCancelled) {
        return;
      }

      if (currentUser.error || !currentUser.data) {
        setAuthState({ user: null, accessToken: null });
        setIsLoading(false);
        return;
      }

      setAuthState({
        user: currentUser.data,
        accessToken,
      });
      setIsLoading(false);
    }

    void restoreSession();

    return () => {
      isCancelled = true;
    };
  }, []);

  return (
    <AuthContext.Provider
      value={{
        user: auth.user,
        token: auth.accessToken,
        isLoading,
        setAuth,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem("gaint_token");
    if (!token) {
      setLoading(false);
      return;
    }
    api("/me")
      .then(setUser)
      .catch(() => localStorage.removeItem("gaint_token"))
      .finally(() => setLoading(false));
  }, []);

  const login = async (credentials) => {
    const result = await api("/auth/login", { method: "POST", body: JSON.stringify(credentials) });
    localStorage.setItem("gaint_token", result.token);
    setUser(result.user);
    return result.user;
  };

  const register = async (formData) => {
    const result = await api("/auth/register", { method: "POST", body: formData });
    localStorage.setItem("gaint_token", result.token);
    setUser(result.user);
    return result.user;
  };

  const refreshUser = async () => {
    const current = await api("/me");
    setUser(current);
    return current;
  };

  const logout = () => {
    localStorage.removeItem("gaint_token");
    setUser(null);
  };

  const value = useMemo(
    () => ({ user, loading, login, register, logout, refreshUser }),
    [user, loading],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}


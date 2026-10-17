import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, getToken, setToken } from "./api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    api("/auth/me")
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    window.addEventListener("auth:expired", logout);
    return () => window.removeEventListener("auth:expired", logout);
  }, [logout]);

  const accept = (res) => {
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  };

  const login = async (email, password) =>
    accept(await api("/auth/login", { method: "POST", body: { email, password } }));

  const register = async (payload) =>
    accept(await api("/auth/register", { method: "POST", body: payload }));

  return (
    <AuthContext.Provider value={{ user, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

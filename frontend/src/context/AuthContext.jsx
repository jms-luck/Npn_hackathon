import { createContext, useContext, useEffect, useState } from "react";
import { api } from "../api/client";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(localStorage.getItem("access_token")));

  useEffect(() => {
    if (!localStorage.getItem("access_token")) return;
    api("/auth/me").then(setUser).catch(() => localStorage.removeItem("access_token")).finally(() => setLoading(false));
  }, []);

  async function login(email, password, role) {
    const result = await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password, role }) });
    localStorage.setItem("access_token", result.access_token);
    const current = await api("/auth/me");
    setUser(current);
    return current;
  }

  function logout() {
    localStorage.removeItem("access_token");
    setUser(null);
  }

  return <AuthContext.Provider value={{ user, loading, login, logout }}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
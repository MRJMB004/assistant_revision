import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api, AUTH_KEY } from "./api";

const AppCtx = createContext(null);
export const useApp = () => useContext(AppCtx);

const THEME_KEY = "reviser:theme";

const load = (key) => {
  try {
    return JSON.parse(localStorage.getItem(key));
  } catch {
    return null;
  }
};
const save = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* stockage indisponible : on ignore */
  }
};

export function AppProvider({ children }) {
  const [auth, setAuthState] = useState(() => load(AUTH_KEY));
  const [user, setUserState] = useState(() => load(AUTH_KEY)?.user ?? null);
  const [sessionReady, setSessionReady] = useState(() => !load(AUTH_KEY)?.access_token);
  const [modules, setModules] = useState([]);
  const [apiOnline, setApiOnline] = useState(null);
  const [toasts, setToasts] = useState([]);
  const [theme, setTheme] = useState(
    () => load(THEME_KEY) || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
  );
  const toastId = useRef(0);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    save(THEME_KEY, theme);
  }, [theme]);
  const toggleTheme = useCallback(() => setTheme((current) => (current === "dark" ? "light" : "dark")), []);

  const toast = useCallback((message, isError = false) => {
    const id = ++toastId.current;
    setToasts((items) => [...items, { id, message, isError }]);
    setTimeout(() => setToasts((items) => items.filter((item) => item.id !== id)), 3800);
  }, []);

  const setAuth = useCallback((session) => {
    setAuthState(session);
    setUserState(session?.user ?? null);
    setSessionReady(true);
    if (session) save(AUTH_KEY, session);
    else localStorage.removeItem(AUTH_KEY);
  }, []);
  const logout = useCallback(() => setAuth(null), [setAuth]);

  useEffect(() => {
    let stopped = false;
    const ping = async () => {
      try {
        await api("/");
        if (!stopped) setApiOnline(true);
      } catch {
        if (!stopped) setApiOnline(false);
      }
    };
    ping();
    const timer = setInterval(ping, 20000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!auth?.access_token) {
      setSessionReady(true);
      return;
    }
    api("/auth/me")
      .then((currentUser) => {
        setUserState(currentUser);
        setAuthState((session) => ({ ...session, user: currentUser }));
      })
      .catch(() => logout())
      .finally(() => setSessionReady(true));
  }, [auth?.access_token, logout]);

  useEffect(() => {
    const onExpired = () => logout();
    window.addEventListener("reviser:auth-expired", onExpired);
    return () => window.removeEventListener("reviser:auth-expired", onExpired);
  }, [logout]);

  const refreshModules = useCallback(async () => {
    if (!user) {
      setModules([]);
      return;
    }
    try {
      setModules(await api("/modules"));
    } catch (err) {
      toast(err.message, true);
    }
  }, [user, toast]);

  useEffect(() => {
    refreshModules();
  }, [refreshModules]);

  const value = useMemo(
    () => ({ user, sessionReady, setAuth, logout, modules, refreshModules, apiOnline, theme, toggleTheme, toast }),
    [user, sessionReady, setAuth, logout, modules, refreshModules, apiOnline, theme, toggleTheme, toast]
  );

  return (
    <AppCtx.Provider value={value}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((item) => <div key={item.id} className={`toast ${item.isError ? "toast-error" : ""}`}>{item.message}</div>)}
      </div>
    </AppCtx.Provider>
  );
}

import { useEffect, useState } from "react";
import Sidebar from "./components/Sidebar.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Setup from "./pages/Setup.jsx";
import Modules from "./pages/Modules.jsx";
import Quiz from "./pages/Quiz.jsx";
import Plan from "./pages/Plan.jsx";
import Resources from "./pages/Resources.jsx";
import Retention from "./pages/Retention.jsx";
import Notifications from "./pages/Notifications.jsx";
import { useApp } from "./AppContext.jsx";

const PAGES = {
  dashboard: Dashboard,
  setup: Setup,
  modules: Modules,
  quiz: Quiz,
  plan: Plan,
  resources: Resources,
  retention: Retention,
  notifs: Notifications,
};

const fromHash = () => {
  const hash = window.location.hash.replace("#", "");
  const path = window.location.pathname.replace(/^\/+|\/+$/g, "").split("/")[0];
  const route = hash || path;
  return route in PAGES ? route : "dashboard";
};

export default function App() {
  const { user, sessionReady } = useApp();
  const [tab, setTab] = useState(fromHash);

  useEffect(() => {
    const onHash = () => setTab(fromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (t) => {
    if (!user && t !== "setup") t = "setup";
    window.location.hash = t;
    setTab(t);
    window.scrollTo({ top: 0 });
  };

  useEffect(() => {
    if (!sessionReady) return;
    if (!user && tab !== "setup") go("setup");
    if (user && tab === "setup") go("dashboard");
  }, [user, sessionReady, tab]);

  if (!sessionReady) {
    return <main className="main"><section className="panel active"><p className="muted">Verification de la session...</p></section></main>;
  }

  const Page = PAGES[tab];
  if (!user) {
    return <Setup onNavigate={go} />;
  }
  return (
    <div className="app">
      <Sidebar tab={tab} onNavigate={go} />
      <main className="main">
        <section className="panel active">
          <Page onNavigate={go} />
        </section>
      </main>
    </div>
  );
}

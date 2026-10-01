import {
  BookOpen, LayoutDashboard, Library, CircleHelp,
  CalendarDays, Compass, TrendingUp, Bell, Moon, Sun, LogOut,
} from "lucide-react";
import { useApp } from "../AppContext.jsx";

const NAV = [
  { id: "dashboard", label: "Tableau de bord", Icon: LayoutDashboard },
  { id: "modules", label: "Modules", Icon: Library },
  { id: "quiz", label: "Quiz diagnostic", Icon: CircleHelp },
  { id: "plan", label: "Planning", Icon: CalendarDays },
  { id: "resources", label: "Ressources", Icon: Compass },
  { id: "retention", label: "Rétention", Icon: TrendingUp },
  { id: "notifs", label: "Notifications", Icon: Bell },
];

export default function Sidebar({ tab, onNavigate }) {
  const { user, logout, apiOnline, theme, toggleTheme } = useApp();
  const status =
    apiOnline === null ? ["", "Vérification de l'API…"]
    : apiOnline ? ["ok", "API connectée"]
    : ["down", "API injoignable"];

  return (
    <aside className="side">
      <div className="brand">
        <span className="brand-mark"><BookOpen size={20} /></span>
        <span className="brand-name">Réviser</span>
      </div>
      <p className="brand-tag">Planning adaptatif</p>

      <nav className="nav">
        {NAV.map(({ id, label, Icon }) => (
          <button
            key={id}
            type="button"
            className={`nav-item ${tab === id ? "active" : ""}`}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => onNavigate(id)}
          >
            <Icon size={18} />
            {label}
          </button>
        ))}
      </nav>

      <div className="side-foot">
        <div className="current-user">{user ? user.name : "Aucun utilisateur sélectionné"}</div>
        <div className={`api-status ${status[0]}`}>{status[1]}</div>
        <button type="button" className="theme-toggle" onClick={toggleTheme} aria-label="Basculer le thème">
          {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
          <span>{theme === "dark" ? "Thème clair" : "Thème sombre"}</span>
        </button>
        {user && <button type="button" className="theme-toggle" onClick={logout}><LogOut size={16} /><span>Se deconnecter</span></button>}
      </div>
    </aside>
  );
}

import { useEffect } from "react";
import { useApp } from "../AppContext.jsx";

export function PanelHead({ eyebrow, title, subtitle }) {
  return (
    <header className="panel-head">
      <div className="eyebrow">{eyebrow}</div>
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </header>
  );
}

/** Affiche `children` seulement si un profil est sélectionné, sinon invite à en choisir un. */
export function RequireUser({ onNavigate, children }) {
  const { user } = useApp();
  if (user) return children;
  return (
    <div className="card-flat empty">
      <h2>Connexion requise</h2>
      <p className="muted">Connecte-toi pour acceder a cette page.</p>
      <button type="button" className="btn-primary" onClick={() => onNavigate("setup")}>
        Se connecter
      </button>
    </div>
  );
}

/** Sélecteur de module qui retombe sur le premier module si la valeur n'existe plus. */
export function ModuleSelect({ modules, value, onChange, id }) {
  useEffect(() => {
    if (modules.length && !modules.some((m) => String(m.id) === String(value))) {
      onChange(String(modules[0].id));
    }
    if (!modules.length && value) onChange("");
  }, [modules, value, onChange]);

  return (
    <label className="select-module">
      Module
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)} disabled={!modules.length}>
        {modules.length === 0 && <option value="">Aucun module</option>}
        {modules.map((m) => (
          <option key={m.id} value={m.id}>
            {m.name}
            {m.course ? ` — ${m.course}` : ""}
          </option>
        ))}
      </select>
    </label>
  );
}

export const formatDate = (iso) =>
  iso
    ? new Date(iso + (iso.length === 10 ? "T00:00:00" : "")).toLocaleDateString("fr-FR", {
        weekday: "short", day: "numeric", month: "long", year: "numeric",
      })
    : "—";

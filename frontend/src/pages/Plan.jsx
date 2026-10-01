import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "../api";
import { useApp } from "../AppContext.jsx";
import { PanelHead, RequireUser } from "../components/ui.jsx";

const DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"];
const priorityClass = (p) => (p.startsWith("Priorité haute") ? "high" : p.startsWith("Priorité moyenne") ? "mid" : "low");

export default function Plan({ onNavigate }) {
  const { user, toast } = useApp();
  const [hours, setHours] = useState("8");
  const [days, setDays] = useState("6");
  const [plan, setPlan] = useState(null);
  const [busy, setBusy] = useState(false);

  // Recharge le dernier planning de l'utilisateur (404 = pas encore de planning)
  useEffect(() => {
    setPlan(null);
    if (!user) return;
    let cancelled = false;
    api("/plans/latest")
      .then((p) => !cancelled && setPlan(p))
      .catch((err) => err.status !== 404 && !cancelled && toast(err.message, true));
    return () => {
      cancelled = true;
    };
  }, [user, toast]);

  const generate = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      setPlan(
        await api("/plans/generate", {
          method: "POST",
          body: { total_hours_per_week: Number(hours), days_per_week: Number(days) },
        })
      );
      toast("Planning généré.");
    } catch (err) {
      toast(err.message, true);
    } finally {
      setBusy(false);
    }
  };

  const byDay = plan ? DAYS.map((d) => ({ day: d, slots: plan.entries.filter((s) => s.day === d) })).filter((d) => d.slots.length) : [];

  return (
    <>
      <PanelHead eyebrow="Semaine" title="Planning de révision" subtitle="Les modules les plus faibles reçoivent le plus de temps." />
      <RequireUser onNavigate={onNavigate}>
        <form className="card-flat inline-form" onSubmit={generate}>
          <label>
            Heures / semaine
            <input type="number" min="1" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} required />
          </label>
          <label>
            Jours / semaine
            <input type="number" min="1" max="7" value={days} onChange={(e) => setDays(e.target.value)} required />
          </label>
          <button type="submit" className="btn-primary" disabled={busy}>
            <Sparkles size={16} /> Générer le planning
          </button>
        </form>

        {!plan && <p className="muted">Aucun planning pour l'instant. Ajoute des modules puis génère-en un.</p>}

        <div className="plan-week">
          {byDay.map(({ day, slots }) => (
            <div className="plan-day" key={day}>
              <div className="plan-day-head">
                <h3>{day}</h3>
                <span className="muted">{slots.reduce((a, s) => a + s.hours, 0).toFixed(1)} h</span>
              </div>
              {slots.map((s, i) => (
                <div className={`plan-slot prio-${priorityClass(s.priority)}`} key={i}>
                  <strong>{s.module_name}</strong>
                  <span>{s.hours} h</span>
                  <small>{s.priority}</small>
                </div>
              ))}
            </div>
          ))}
        </div>
      </RequireUser>
    </>
  );
}

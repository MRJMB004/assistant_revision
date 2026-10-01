import { useCallback, useEffect, useState } from "react";
import { Send } from "lucide-react";
import { api } from "../api";
import { useApp } from "../AppContext.jsx";
import { PanelHead, RequireUser } from "../components/ui.jsx";

export default function Notifications({ onNavigate }) {
  const { user, toast } = useApp();
  const [notifs, setNotifs] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!user) return setNotifs([]);
    try {
      setNotifs(await api("/notifications"));
    } catch (err) {
      toast(err.message, true);
    }
  }, [user, toast]);

  useEffect(() => {
    load();
  }, [load]);

  const send = async () => {
    setBusy(true);
    try {
      const notification = await api("/notifications/send", { method: "POST" });
      toast(notification.simulated === "true" ? "Notification enregistree : SMTP n'est pas encore configure." : "E-mail envoye.");
      await load();
    } catch (err) {
      toast(err.message, true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PanelHead eyebrow="Rappels" title="Notifications" subtitle="Planning hebdomadaire et revisions a rattraper par e-mail." />
      <RequireUser onNavigate={onNavigate}>
        <button type="button" className="btn-primary" onClick={send} disabled={busy}>
          <Send size={16} /> Envoyer le rappel par e-mail
        </button>

        <div className="stack-list">
          {notifs.length === 0 && <p className="muted">Aucune notification envoyée pour l'instant.</p>}
          {notifs.map((n) => (
            <article className="card-flat notif" key={n.id}>
              <header>
                <h3>{n.subject}</h3>
                <time className="muted" dateTime={n.sent_at}>
                  {new Date(n.sent_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}
                </time>
              </header>
              <pre className="notif-body">{n.body}</pre>
              <span className="badge">{n.simulated === "true" ? "Simulation locale" : "E-mail envoye"}</span>
            </article>
          ))}
        </div>
      </RequireUser>
    </>
  );
}

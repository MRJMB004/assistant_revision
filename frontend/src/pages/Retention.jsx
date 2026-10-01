import { useMemo, useState } from "react";
import { useApp } from "../AppContext.jsx";
import { useRetention } from "../hooks.js";
import { getAverageRetentionTimeline, getRetentionTimeline, getStatus } from "../retention.js";
import { PanelHead, RequireUser, formatDate } from "../components/ui.jsx";

const toneFor = (retention) => (retention >= 0.8 ? "green" : retention >= 0.5 ? "amber" : "red");
const labelDate = (date) => new Intl.DateTimeFormat("fr-FR", { day: "numeric", month: "short" }).format(date);

function monthTicks(start, end) {
  if (!start || !end) return [];
  const ticks = [{ date: start, label: labelDate(start), monthEnd: false }];
  const cursor = new Date(start.getFullYear(), start.getMonth() + 1, 0);
  while (cursor <= end) {
    if (cursor > start) ticks.push({ date: new Date(cursor), label: labelDate(cursor), monthEnd: true });
    cursor.setMonth(cursor.getMonth() + 2, 0);
  }
  if (ticks.at(-1).date.getTime() !== end.getTime()) ticks.push({ date: end, label: labelDate(end), monthEnd: false });
  return ticks;
}

function RetentionChart({ points, now }) {
  if (!points.length) return <p className="muted">Aucune courbe a afficher tant qu'un quiz n'a pas ete termine.</p>;
  const width = 820;
  const height = 310;
  const chart = { left: 62, top: 22, right: 786, bottom: 246 };
  const start = points[0].date;
  const end = points.at(-1).date;
  const dayRange = Math.max(1, (end - start) / 86400000);
  const x = (date) => chart.left + ((date - start) / 86400000 / dayRange) * (chart.right - chart.left);
  const y = (value) => chart.bottom - (value / 100) * (chart.bottom - chart.top);
  const polyline = points.map((point) => `${x(point.date)},${y(point.value)}`).join(" ");
  const today = new Date(now);
  today.setHours(0, 0, 0, 0);
  const todayX = x(Math.min(Math.max(today, start), end));
  const ticks = monthTicks(start, end);

  return (
    <div className="retention-chart-frame">
      <svg className="retention-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Evolution quotidienne de la retention estimee">
        <text className="retention-axis-title" x="17" y={(chart.top + chart.bottom) / 2} transform={`rotate(-90 17 ${(chart.top + chart.bottom) / 2})`}>Retention estimee (%)</text>
        {[0, 25, 50, 75, 100].map((value) => <g key={value}><line className="retention-grid" x1={chart.left} x2={chart.right} y1={y(value)} y2={y(value)} /><text className="retention-y-label" x={chart.left - 10} y={y(value) + 4}>{value}</text></g>)}
        <line className="retention-threshold" x1={chart.left} x2={chart.right} y1={y(90)} y2={y(90)} />
        <text className="retention-threshold-label" x={chart.right - 2} y={y(90) - 6}>Seuil 90 %</text>
        <line className="retention-today-line" x1={todayX} x2={todayX} y1={chart.top} y2={chart.bottom} />
        <text className="retention-today-label" x={todayX} y={chart.top - 7} textAnchor="middle">Aujourd'hui</text>
        <polyline className="retention-history-line" points={polyline} />
        {ticks.map((tick) => <g key={tick.date.toISOString()}><line className="retention-x-tick" x1={x(tick.date)} x2={x(tick.date)} y1={chart.bottom} y2={chart.bottom + 5} /><text className={`retention-x-label ${tick.monthEnd ? "month-end" : ""}`} x={x(tick.date)} y={chart.bottom + 23} textAnchor="middle">{tick.label}</text></g>)}
      </svg>
    </div>
  );
}

export default function Retention({ onNavigate }) {
  const { modules } = useApp();
  const { data, loading, error } = useRetention(modules);
  const [selectedModule, setSelectedModule] = useState("all");
  const now = useMemo(() => new Date(), []);
  const rows = useMemo(() => data.map((item) => ({ ...item, status: getStatus(item.history, now) })).sort((left, right) => (left.status.retention ?? 2) - (right.status.retention ?? 2)), [data, now]);
  const chartPoints = useMemo(() => selectedModule === "all" ? getAverageRetentionTimeline(rows.map((item) => item.history), now) : getRetentionTimeline(rows.find((item) => String(item.module_id) === selectedModule)?.history ?? [], now), [rows, selectedModule, now]);

  return (
    <>
      <PanelHead eyebrow="Suivi" title="Courbe de retention" subtitle="L'estimation evolue avec les quiz termines et le temps ecoule." />
      <RequireUser onNavigate={onNavigate}>
        <section className="card-flat retention-chart-card">
          <div className="retention-chart-head"><div><h2>Evolution dans le temps</h2><p className="muted">Le score remonte apres chaque quiz puis baisse jour apres jour.</p></div><label>Module<select value={selectedModule} onChange={(event) => setSelectedModule(event.target.value)}><option value="all">Tous (moyenne)</option>{rows.map((item) => <option key={item.module_id} value={item.module_id}>{item.module_name}</option>)}</select></label></div>
          <RetentionChart points={chartPoints} now={now} />
        </section>
        <div className="stack-list">
          {modules.length === 0 && <p className="muted">Ajoute d'abord des modules.</p>}
          {loading && rows.length === 0 && <p className="muted">Calcul de la retention en cours...</p>}
          {error && <p className="muted">Impossible de charger le suivi : {error}</p>}
          {rows.map((item) => {
            const { status } = item;
            if (status.retention === null) return <article className="card-flat retention-card" key={item.module_id}><h3>{item.module_name}</h3><p className="muted">Pas encore d'historique. Passe un quiz pour lancer la courbe de retention.</p></article>;
            const tone = toneFor(status.retention);
            return <article className="card-flat retention-card" key={item.module_id}><div className="retention-card-head"><div><h3>{item.module_name}</h3><p className="muted">Intervalle actuel : {status.interval} j · {status.reps} reussite{status.reps > 1 ? "s" : ""} d'affilee</p></div><strong className={`retention-percent tone-${tone}`}>{Math.round(status.retention * 100)} %</strong></div><div className="retention-card-foot">{status.overdueDays > 0 ? <strong className="retention-overdue">En retard de {status.overdueDays} j</strong> : <span>Prochaine revision le {formatDate(status.nextDate.toISOString().slice(0, 10))}</span>}</div></article>;
          })}
        </div>
      </RequireUser>
    </>
  );
}

import { useMemo } from "react";
import { Bar } from "react-chartjs-2";
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, Tooltip } from "chart.js";
import { Library, Target, TriangleAlert, CircleCheck } from "lucide-react";
import { useApp } from "../AppContext.jsx";
import { useRetention } from "../hooks.js";
import { PanelHead } from "../components/ui.jsx";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip);

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

export default function Dashboard() {
  const { user, modules, theme } = useApp();
  const { data } = useRetention(modules);

  const scores = data.map((d) => d.last_score).filter((s) => s !== null);
  const avg = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null;
  const weak = data.filter((d) => d.last_score === null || d.last_score < 50).length;
  const mastered = data.filter((d) => d.last_score !== null && d.last_score >= 80).length;

  const chart = useMemo(() => {
    const ink = cssVar("--ink-soft");
    const line = cssVar("--line");
    const colorFor = (s) => (s === null || s < 50 ? cssVar("--red") : s < 80 ? cssVar("--amber") : cssVar("--green"));
    return {
      data: {
        labels: data.map((d) => d.module_name),
        datasets: [{
          data: data.map((d) => d.last_score ?? 0),
          backgroundColor: data.map((d) => colorFor(d.last_score)),
          borderRadius: 6,
          maxBarThickness: 48,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => (data[ctx.dataIndex].last_score === null ? "Pas encore évalué" : `${ctx.parsed.y} %`),
            },
          },
        },
        scales: {
          y: { min: 0, max: 100, ticks: { color: ink, callback: (v) => `${v} %` }, grid: { color: line } },
          x: { ticks: { color: ink }, grid: { display: false } },
        },
      },
    };
    // `theme` force le recalcul des couleurs quand on bascule clair/sombre
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, theme]);

  const stats = [
    { Icon: Library, tone: "blue", value: modules.length, label: "Modules actifs" },
    { Icon: Target, tone: "amber", value: avg === null ? "—" : `${avg} %`, label: "Score moyen (dernier quiz)" },
    { Icon: TriangleAlert, tone: "red", value: weak, label: "Modules à prioriser" },
    { Icon: CircleCheck, tone: "green", value: mastered, label: "Modules maîtrisés" },
  ];

  return (
    <>
      <PanelHead
        eyebrow="Vue d'ensemble"
        title={user ? `Bonjour, ${user.name}.` : "Bienvenue."}
        subtitle={user ? "Voici où tu en es dans tes révisions." : "Sélectionne un profil pour voir tes statistiques."}
      />

      <div className="stats-grid">
        {stats.map(({ Icon, tone, value, label }) => (
          <div className="stat-card" key={label}>
            <div className={`stat-icon accent-${tone}`}><Icon size={20} /></div>
            <div className="stat-body">
              <div className="stat-value">{value}</div>
              <div className="stat-label">{label}</div>
            </div>
          </div>
        ))}
      </div>

      <div className="card-flat chart-card">
        <div className="chart-head">
          <h2>Progression par module</h2>
          <span className="muted">
            {data.length ? "Dernier score obtenu à chaque quiz." : "Ajoute des modules et passe des quiz pour voir la courbe."}
          </span>
        </div>
        <div className="chart-wrap">
          {data.length > 0 && <Bar data={chart.data} options={chart.options} />}
        </div>
      </div>
    </>
  );
}

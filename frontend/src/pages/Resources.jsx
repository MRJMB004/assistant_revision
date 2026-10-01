import { useEffect, useState } from "react";
import {
  FileText, CirclePlay, GraduationCap, Book, Pencil, MessageCircle,
  BookOpen, Search, Link as LinkIcon, ExternalLink,
} from "lucide-react";
import { api, safeUrl } from "../api";
import { useApp } from "../AppContext.jsx";
import { PanelHead, RequireUser, ModuleSelect } from "../components/ui.jsx";

const TYPE_ICON = {
  "PDF": FileText,
  "PDF académique": FileText,
  "vidéo": CirclePlay,
  "cours vidéo": CirclePlay,
  "cours": GraduationCap,
  "documentation": Book,
  "exercices": Pencil,
  "forum Q&A": MessageCircle,
  "encyclopédie": BookOpen,
  "recherche": Search,
};

export default function Resources({ onNavigate }) {
  const { modules, toast } = useApp();
  const [moduleId, setModuleId] = useState("");
  const [courses, setCourses] = useState([]);
  const [courseId, setCourseId] = useState("");
  const [coursesLoaded, setCoursesLoaded] = useState(false);
  const [resources, setResources] = useState(null); // null = pas chargé
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setCourses([]);
    setCourseId("");
    setCoursesLoaded(false);
    if (!moduleId) return;
    let cancelled = false;
    api(`/modules/${moduleId}/courses`)
      .then((items) => {
        if (cancelled) return;
        setCourses(items);
        setCourseId(String(items[0]?.id || ""));
        setCoursesLoaded(true);
      })
      .catch((err) => !cancelled && toast(err.message, true));
    return () => { cancelled = true; };
  }, [moduleId, toast]);

  useEffect(() => {
    setResources(null);
    setError("");
    if (!moduleId || !coursesLoaded || (courses.length > 0 && !courseId)) return;
    let cancelled = false;
    setLoading(true);
    api(`/modules/${moduleId}/resources${courseId ? `?course_id=${courseId}` : ""}`)
      .then((r) => !cancelled && setResources(r))
      .catch((err) => {
        if (cancelled) return;
        setError(err.message);
        toast(err.message, true);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [moduleId, courseId, courses.length, coursesLoaded, toast]);

  return (
    <>
      <PanelHead eyebrow="Bonus" title="Ressources recommandées" subtitle="Suggestions par mots-clés à partir du nom et du cours du module." />
      <RequireUser onNavigate={onNavigate}>
        <ModuleSelect modules={modules} value={moduleId} onChange={setModuleId} />
        {moduleId && courses.length > 0 && <label className="select-module">Cours<select value={courseId} onChange={(event) => setCourseId(event.target.value)}>{courses.map((course) => <option key={course.id} value={course.id}>{course.subject}</option>)}</select></label>}

        <div className="stack-list">
          {!moduleId && <p className="muted">Sélectionne un module.</p>}
          {loading && <p className="muted">🔎 Recherche de ressources en cours…</p>}
          {error && <p className="muted">Erreur : {error}</p>}
          {resources && resources.length === 0 && (
            <p className="muted">Aucune ressource trouvée. Essaie de reformuler le nom du module.</p>
          )}
          {resources && resources.length > 0 && (
            <>
              <div className="resources-head">
                <span className="muted">{resources.length} ressource(s) suggérée(s)</span>
              </div>
              {resources.map((r, i) => {
                const Icon = TYPE_ICON[r.type] || LinkIcon;
                const href = safeUrl(r.url);
                return (
                  <div className="resource-row" key={`${r.url}-${i}`}>
                    <div className="resource-icon"><Icon /></div>
                    <div className="resource-body">
                      <a href={href} target="_blank" rel="noopener noreferrer" className="resource-title">{r.title}</a>
                      <div className="resource-meta">
                        <span className="resource-type">{r.type}</span>
                        {r.lang && <span className="resource-lang">{r.lang.toUpperCase()}</span>}
                      </div>
                    </div>
                    <a href={href} target="_blank" rel="noopener noreferrer" className="resource-open" aria-label="Ouvrir">
                      <ExternalLink />
                    </a>
                  </div>
                );
              })}
            </>
          )}
        </div>
      </RequireUser>
    </>
  );
}

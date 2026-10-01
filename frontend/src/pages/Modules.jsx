import { useCallback, useEffect, useState } from "react";
import { BookOpen, ChevronDown, Pencil, Plus, Sparkles, Trash2 } from "lucide-react";
import { api } from "../api";
import { useApp } from "../AppContext.jsx";
import { ModuleSelect, PanelHead, RequireUser } from "../components/ui.jsx";

const splitLines = (value) => value.split("\n").map((item) => item.trim()).filter(Boolean);

export default function Modules({ onNavigate }) {
  const { user, modules, refreshModules, toast } = useApp();
  const [name, setName] = useState("");
  const [course, setCourse] = useState("");
  const [hours, setHours] = useState("2");
  const [busy, setBusy] = useState(false);
  const [moduleId, setModuleId] = useState("");
  const [courses, setCourses] = useState([]);
  const [coursesLoading, setCoursesLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [subject, setSubject] = useState("");
  const [level, setLevel] = useState("Intermediaire");
  const [language, setLanguage] = useState("Francais");
  const [length, setLength] = useState("800");
  const [objectives, setObjectives] = useState("");
  const [editingCourse, setEditingCourse] = useState(null);
  const [movingCourse, setMovingCourse] = useState(null);

  const loadCourses = useCallback(async () => {
    if (!moduleId) {
      setCourses([]);
      return;
    }
    setCoursesLoading(true);
    try {
      setCourses(await api(`/modules/${moduleId}/courses`));
    } catch (err) {
      toast(err.message, true);
    } finally {
      setCoursesLoading(false);
    }
  }, [moduleId, toast]);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  const create = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api("/modules", {
        method: "POST",
        body: { name: name.trim(), course: course.trim() || null, weekly_objective_hours: Number(hours) },
      });
      setName("");
      setCourse("");
      setHours("2");
      toast("Module ajoute.");
      await refreshModules();
    } catch (err) {
      toast(err.message, true);
    } finally {
      setBusy(false);
    }
  };

  const remove = async (m) => {
    if (!window.confirm(`Supprimer le module "${m.name}" ?`)) return;
    try {
      await api(`/modules/${m.id}`, { method: "DELETE" });
      toast("Module supprime.");
      await refreshModules();
    } catch (err) {
      toast(err.message, true);
    }
  };

  const generateCourse = async (e) => {
    e.preventDefault();
    const parsedObjectives = splitLines(objectives);
    if (!parsedObjectives.length) return toast("Ajoute au moins un objectif, un par ligne.", true);
    setGenerating(true);
    try {
      const generated = await api(`/modules/${moduleId}/courses/generate`, {
        method: "POST",
        body: { subject: subject.trim(), level: level.trim(), language: language.trim(), desired_length: Number(length), objectives: parsedObjectives, chapters: [] },
      });
      setCourses((items) => [generated, ...items]);
      setSubject("");
      setObjectives("");
      toast("Cours genere et enregistre.");
    } catch (err) {
      toast(err.message, true);
    } finally {
      setGenerating(false);
    }
  };

  const saveCourse = async (event) => {
    event.preventDefault();
    try {
      const updated = await api(`/courses/${editingCourse.id}`, { method: "PATCH", body: { subject: editingCourse.subject, content: editingCourse.content } });
      setCourses((items) => items.map((item) => item.id === updated.id ? updated : item));
      setEditingCourse(null); toast("Cours modifie.");
    } catch (err) { toast(err.message, true); }
  };
  const deleteCourse = async (courseItem) => {
    if (!window.confirm(`Supprimer le cours "${courseItem.subject}" et son parcours ?`)) return;
    try { await api(`/courses/${courseItem.id}`, { method: "DELETE" }); setCourses((items) => items.filter((item) => item.id !== courseItem.id)); toast("Cours et donnees liees supprimes."); }
    catch (err) { toast(err.message, true); }
  };
  const moveCourse = async (event) => {
    event.preventDefault();
    try {
      await api(`/courses/${movingCourse.id}/move`, { method: "POST", body: { module_id: Number(movingCourse.moduleId) } });
      setCourses((items) => items.filter((item) => item.id !== movingCourse.id)); setMovingCourse(null); toast("Cours deplace avec son parcours.");
    } catch (err) { toast(err.message, true); }
  };

  return (
    <>
      <PanelHead eyebrow="Organisation" title="Modules & cours" subtitle="Organise tes matieres puis genere des cours adaptes a tes objectifs." />
      <RequireUser onNavigate={onNavigate}>
        <div className="grid-2">
          <form className="card-flat" onSubmit={create}>
            <h2>Nouveau module</h2>
            <label>Nom du module<input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Ex. Mathematiques" required /></label>
            <label>Cours / matiere<input type="text" value={course} onChange={(e) => setCourse(e.target.value)} placeholder="Ex. Algebre lineaire" /></label>
            <label>Objectif hebdo (heures)<input type="number" min="0.5" step="0.5" value={hours} onChange={(e) => setHours(e.target.value)} required /></label>
            <button type="submit" className="btn-primary" disabled={busy}><Plus size={16} /> Ajouter le module</button>
          </form>

          <div className="card-flat">
            <h2>Mes modules</h2>
            <div className="stack-list">
              {modules.length === 0 && <p className="muted">Aucun module pour l'instant.</p>}
              {modules.map((m) => (
                <div className="list-row" key={m.id}>
                  <div className="list-row-body"><strong>{m.name}</strong><small className="muted">{m.course ? `${m.course} · ` : ""}{m.weekly_objective_hours} h / semaine</small></div>
                  <button type="button" className="icon-btn danger" aria-label={`Supprimer ${m.name}`} onClick={() => remove(m)}><Trash2 size={16} /></button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <section className="course-workspace">
          <div className="course-workspace-head">
            <div><div className="eyebrow">Cours IA</div><h2>Generer un cours</h2></div>
            <ModuleSelect modules={modules} value={moduleId} onChange={setModuleId} id="course-module" />
          </div>
          {!moduleId ? <p className="muted">Selectionne un module pour creer ou consulter ses cours.</p> : (
            <div className="grid-2">
              <form className="card-flat" onSubmit={generateCourse}>
                <label>Sujet<input type="text" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Ex. Derivees" required /></label>
                <label>Niveau<select value={level} onChange={(e) => setLevel(e.target.value)}><option value="Debutant">Debutant</option><option value="Intermediaire">Intermediaire</option><option value="Avance">Avance</option><option value="Experimente">Experimente</option></select></label>
                <label>Langue<select value={language} onChange={(e) => setLanguage(e.target.value)}><option value="Francais">Francais</option><option value="Anglais">Anglais</option><option value="Espagnol">Espagnol</option><option value="Arabe">Arabe</option><option value="Allemand">Allemand</option><option value="Italien">Italien</option><option value="Portugais">Portugais</option><option value="Russe">Russe</option><option value="Chinois">Chinois</option><option value="Japonais">Japonais</option></select></label>
                <label>Longueur souhaitee (mots)<input type="number" min="300" max="10000" step="100" value={length} onChange={(e) => setLength(e.target.value)} required /></label>
                <label>Objectifs (un par ligne)<textarea rows={4} value={objectives} onChange={(e) => setObjectives(e.target.value)} placeholder={"Comprendre les notions de base\nSavoir resoudre un exercice"} required /></label>
                <button type="submit" className="btn-primary" disabled={generating}><Sparkles size={16} /> {generating ? "Generation..." : "Generer le cours"}</button>
              </form>

              <div className="card-flat course-library">
                <h2>Cours enregistres</h2>
                {coursesLoading && <p className="muted">Chargement des cours...</p>}
                {!coursesLoading && courses.length === 0 && <p className="muted">Aucun cours genere pour ce module.</p>}
                <div className="stack-list">
                  {courses.map((item) => (
                    <details className="course-item" key={item.id}>
                      <summary><span className="course-item-title"><BookOpen size={17} /> {item.subject}</span><ChevronDown size={17} /></summary>
                      <div className="course-meta muted">{item.level} · {item.language} · {item.desired_length} mots</div>
                      <div className="course-detail">
                        <div className="course-actions"><button type="button" className="icon-btn" aria-label={`Modifier ${item.subject}`} onClick={() => setEditingCourse({ ...item })}><Pencil size={16} /></button><button type="button" className="icon-btn" aria-label={`Deplacer ${item.subject}`} onClick={() => setMovingCourse({ id: item.id, moduleId: String(item.module_id) })}>Deplacer</button><button type="button" className="icon-btn danger" aria-label={`Supprimer ${item.subject}`} onClick={() => deleteCourse(item)}><Trash2 size={16} /></button></div>
                        <h3>Objectifs</h3><ul>{item.objectives.map((objective, index) => <li key={index}>{objective}</li>)}</ul>
                        {item.chapters.map((chapter, index) => <article className="course-chapter" key={`${chapter.title}-${index}`}><h3>{chapter.title}</h3><p>{chapter.explanation}</p>{chapter.examples.length > 0 && <p className="muted"><strong>Exemples :</strong> {chapter.examples.join(" · ")}</p>}</article>)}
                        <h3>Resume</h3><p>{item.summary}</p>
                      </div>
                    </details>
                  ))}
                </div>
                {editingCourse && <form className="course-editor" onSubmit={saveCourse}><h3>Modifier le cours</h3><label>Titre<input value={editingCourse.subject} onChange={(e) => setEditingCourse((item) => ({ ...item, subject: e.target.value }))} required /></label><label>Contenu<textarea rows={8} value={editingCourse.content} onChange={(e) => setEditingCourse((item) => ({ ...item, content: e.target.value }))} required /></label><button className="btn-primary">Enregistrer</button><button type="button" className="btn-ghost" onClick={() => setEditingCourse(null)}>Annuler</button></form>}
                {movingCourse && <form className="course-editor" onSubmit={moveCourse}><h3>Deplacer le cours</h3><label>Module de destination<select value={movingCourse.moduleId} onChange={(e) => setMovingCourse((item) => ({ ...item, moduleId: e.target.value }))}>{modules.map((module) => <option key={module.id} value={module.id}>{module.name}</option>)}</select></label><button className="btn-primary">Deplacer</button><button type="button" className="btn-ghost" onClick={() => setMovingCourse(null)}>Annuler</button></form>}
              </div>
            </div>
          )}
        </section>
      </RequireUser>
    </>
  );
}

import { useCallback, useEffect, useRef, useState } from "react";
import { BarChart3, CheckCircle2, ClipboardCheck, Lock, Play, RotateCcw, Sparkles } from "lucide-react";
import { api } from "../api";
import { useApp } from "../AppContext.jsx";
import { ModuleSelect, PanelHead, RequireUser } from "../components/ui.jsx";

const formatAttemptDate = (value) => new Date(value).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" });

export default function Quiz({ onNavigate }) {
  const { user, modules, toast } = useApp();
  const [moduleId, setModuleId] = useState("");
  const [courses, setCourses] = useState([]);
  const [courseId, setCourseId] = useState("");
  const [levels, setLevels] = useState([]);
  const [activeLevel, setActiveLevel] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null);
  const [loadingQuestions, setLoadingQuestions] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [attempts, setAttempts] = useState([]);
  const [stats, setStats] = useState(null);
  const [review, setReview] = useState([]);
  const [trackingLoading, setTrackingLoading] = useState(false);
  const [showAllReview, setShowAllReview] = useState(false);
  const courseRequest = useRef(0);
  const levelsRequest = useRef(0);
  const trackingRequest = useRef(0);
  const selectedCourseId = Number(courseId);
  const hasSelectedCourse = Number.isInteger(selectedCourseId) && selectedCourseId > 0;
  const visibleReview = review.slice(0, showAllReview ? 5 : 3);

  const loadCourses = useCallback(async () => {
    if (!moduleId) return setCourses([]);
    const requestId = ++courseRequest.current;
    try {
      const items = await api(`/modules/${moduleId}/courses`);
      if (requestId !== courseRequest.current) return;
      setCourses(items);
      setCourseId((current) => items.some((item) => String(item.id) === String(current)) ? current : String(items[0]?.id || ""));
    } catch (err) { toast(err.message, true); }
  }, [moduleId, toast]);

  const loadLevels = useCallback(async () => {
    if (!moduleId || !hasSelectedCourse) return setLevels([]);
    const requestId = ++levelsRequest.current;
    try {
      const response = await api(`/modules/${moduleId}/quiz/levels?course_id=${selectedCourseId}`);
      if (requestId === levelsRequest.current) setLevels(response.levels);
    }
    catch (err) { toast(err.message, true); }
  }, [moduleId, hasSelectedCourse, selectedCourseId, toast]);

  const loadTracking = useCallback(async () => {
    const requestId = ++trackingRequest.current;
    if (!moduleId || !user || !hasSelectedCourse) {
      setAttempts([]); setStats(null); setReview([]);
      return;
    }
    setTrackingLoading(true);
    try {
      const [attemptItems, statItem, reviewItems] = await Promise.all([
        api(`/modules/${moduleId}/quiz/attempts?course_id=${selectedCourseId}`), api(`/modules/${moduleId}/quiz/stats?course_id=${selectedCourseId}`), api(`/modules/${moduleId}/quiz/review?course_id=${selectedCourseId}`),
      ]);
      if (requestId !== trackingRequest.current) return;
      setAttempts(attemptItems); setStats(statItem); setReview(reviewItems);
    } catch (err) { toast(err.message, true); }
    finally { setTrackingLoading(false); }
  }, [moduleId, hasSelectedCourse, selectedCourseId, toast, user]);

  useEffect(() => {
    loadCourses();
  }, [loadCourses]);

  useEffect(() => {
    loadLevels(); loadTracking();
  }, [loadLevels, loadTracking]);

  const changeModule = (nextModuleId) => {
    courseRequest.current += 1; levelsRequest.current += 1; trackingRequest.current += 1;
    setModuleId(nextModuleId); setCourseId(""); setActiveLevel(null); setQuestions([]); setAnswers({}); setResult(null);
  };

  const changeCourse = (nextCourseId) => {
    levelsRequest.current += 1; trackingRequest.current += 1;
    setCourseId(nextCourseId); setActiveLevel(null); setQuestions([]); setResult(null); setShowAllReview(false);
  };

  const startLevel = async (level) => {
    if (!moduleId || !level?.unlocked) return;
    setLoadingQuestions(true); setResult(null); setAnswers({});
    try {
      const session = await api(`/modules/${moduleId}/quiz/levels/${level.level}/start`, {
        method: "POST", body: { course_id: hasSelectedCourse ? selectedCourseId : null },
      });
      setActiveLevel(session.level); setQuestions(session.questions);
    } catch (err) { toast(err.message, true); }
    finally { setLoadingQuestions(false); }
  };


  const submitQuiz = async (event) => {
    event.preventDefault();
    if (questions.some((question) => answers[question.id] === undefined)) return toast("Reponds aux 5 questions avant de valider.", true);
    setSubmitting(true);
    try {
      const submitted = await api(`/modules/${moduleId}/quiz/submit`, {
        method: "POST",
        body: { course_id: selectedCourseId, level: activeLevel, answers: questions.map((question) => ({ question_id: question.id, selected_index: answers[question.id] })) },
      });
      setResult(submitted); await Promise.all([loadLevels(), loadTracking()]);
    } catch (err) { toast(err.message, true); }
    finally { setSubmitting(false); }
  };

  const replay = () => startLevel(levels.find((level) => level.level === activeLevel));
  const nextLevel = () => startLevel(levels.find((level) => level.level === activeLevel + 1));
  const tone = result ? (result.passed ? "green" : "red") : "";

  return <>
    <PanelHead eyebrow="Diagnostic" title="Quiz par niveaux" subtitle="5 questions par niveau. Obtiens 80 % pour debloquer le suivant." />
    <RequireUser onNavigate={onNavigate}>
      <ModuleSelect modules={modules} value={moduleId} onChange={changeModule} />
      {!moduleId ? <p className="muted">Selectionne un module pour commencer.</p> : <>
        <section className="card-flat level-board">
          <div className="level-head"><div><div className="eyebrow">Parcours</div><h2>50 niveaux</h2><span className="muted">Niveau atteint : {stats?.level_reached ?? 1}/50</span></div><aside className="review-compact"><div><strong>A consolider ({review.length})</strong>{review.length > 3 && <button type="button" className="btn-ghost" onClick={() => setShowAllReview((value) => !value)}>{showAllReview ? "Reduire" : "Tout voir"}</button>}</div>{visibleReview.map((item) => <details key={item.question_id}><summary title={item.notion}><span>{item.notion}</span><b title={`${item.mistake_count} fois`}>{item.mistake_count}x</b></summary><p><strong>Reponse attendue :</strong> {item.correct_answer}<br />{item.explanation}</p></details>)}{review.length === 0 && <small className="muted">Rien a consolider pour ce cours.</small>}</aside></div>
          <label>Cours pour les nouvelles questions<select value={courseId} onChange={(event) => changeCourse(event.target.value)}><option value="">Selectionner un cours</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.subject}</option>)}</select></label>
          <div className="level-grid">{levels.map((level) => <button type="button" key={level.level} className={`level-card ${level.unlocked ? "unlocked" : "locked"} ${level.passed ? "passed" : ""}`} disabled={!level.unlocked || loadingQuestions} onClick={() => startLevel(level)}>
            {level.passed ? <CheckCircle2 size={17} /> : level.unlocked ? <Play size={17} /> : <Lock size={17} />}<strong>Niveau {level.level}</strong><small>{level.best_correct == null ? (level.unlocked ? "A jouer" : "Verrouille") : `${level.best_correct}/${level.total_questions}`}</small>
          </button>)}</div>
        </section>
        <div className="quiz-tools card-flat"><h2>Generation adaptee</h2><p className="muted">Le serveur genere 5 questions nouvelles selon le niveau: bases, application directe, puis cas pratiques et calculs.</p><button type="button" className="btn-primary" disabled={!levels.find((level) => level.current) || loadingQuestions} onClick={() => startLevel(levels.find((level) => level.current))}><Sparkles size={16} /> Jouer le niveau actuel</button></div>
        <section className="quiz-session card-flat"><div className="section-head"><div><div className="eyebrow">Session</div><h2>{activeLevel ? `Niveau ${activeLevel}` : "Choisis un niveau"}</h2></div>{questions.length > 0 && <span className="muted">5 questions</span>}</div>
          {loadingQuestions ? <p className="muted">Preparation de nouvelles questions...</p> : !activeLevel ? <p className="muted">Les niveaux verrouilles sont proteges aussi par le serveur.</p> : result ? <><div className={`quiz-result tone-${tone}`}><div className="quiz-score">{Math.round(result.score)} %</div><p><strong>{result.passed ? "Niveau reussi, niveau suivant debloque." : "Encore un effort : il faut 4/5 minimum pour passer au niveau suivant."}</strong></p><p className="muted">{result.correct}/5 bonnes reponses.</p><p className="muted">{result.consolidated_count > 0 ? `${result.consolidated_count} ${result.consolidated_count === 1 ? "notion consolidee" : "notions consolidees"}.` : result.remaining_review_count > 0 ? `Il reste ${result.remaining_review_count} ${result.remaining_review_count === 1 ? "notion a consolider" : "notions a consolider"}.` : "Rien a consolider, bravo."}</p><div className="result-actions"><button type="button" className="btn-ghost" onClick={replay}><RotateCcw size={16} /> Rejouer ce niveau</button><button type="button" className="btn-primary" disabled={!result.next_level_unlocked || activeLevel === 50} onClick={nextLevel}><Play size={16} /> Niveau suivant</button></div></div><div className="result-list">{result.results.map((item) => <article className={`result-item ${item.is_correct ? "correct" : "incorrect"}`} key={item.question_id}><div className="result-item-head"><strong>{item.question}</strong><span>{item.is_correct ? "Correct" : "A consolider"}</span></div><p>Ta reponse : {item.selected_answer}</p>{!item.is_correct && <p><strong>Bonne reponse : </strong>{item.correct_answer}</p>}<p className="muted">{item.explanation}</p></article>)}</div></> : <form onSubmit={submitQuiz} className="quiz-runner">{questions.map((question, index) => <fieldset key={question.id} className="quiz-q"><legend>{index + 1}. {question.question}</legend>{question.choices.map((choice, choiceIndex) => <label key={choiceIndex} className={`choice ${answers[question.id] === choiceIndex ? "picked" : ""}`}><input type="radio" name={`q-${question.id}`} checked={answers[question.id] === choiceIndex} onChange={() => setAnswers((current) => ({ ...current, [question.id]: choiceIndex }))} /><span>{choice}</span></label>)}</fieldset>)}<button type="submit" className="btn-primary" disabled={submitting}><ClipboardCheck size={16} /> {submitting ? "Validation..." : "Valider mes reponses"}</button></form>}</section>
        <section className="quiz-followup"><div className="section-head"><div><div className="eyebrow">Suivi</div><h2>Progression du cours</h2></div><BarChart3 size={20} className="muted" /></div>{trackingLoading ? <p className="muted">Chargement du suivi...</p> : <><div className="stats-grid quiz-stats"><div className="stat-card"><div className="stat-body"><div className="stat-value">{stats?.level_reached ?? 1}</div><div className="stat-label">Niveau atteint</div></div></div><div className="stat-card"><div className="stat-body"><div className="stat-value">{stats?.average_score == null ? "-" : `${Math.round(stats.average_score)} %`}</div><div className="stat-label">Moyenne</div></div></div><div className="stat-card"><div className="stat-body"><div className="stat-value">{stats?.best_score == null ? "-" : `${Math.round(stats.best_score)} %`}</div><div className="stat-label">Meilleur score</div></div></div></div><div className="card-flat"><h3>Historique</h3>{attempts.length === 0 ? <p className="muted">Aucune tentative.</p> : <div className="stack-list">{attempts.map((attempt) => <div className="attempt-row" key={attempt.id}><span>{formatAttemptDate(attempt.date)}{attempt.level ? ` - N${attempt.level}` : ""}</span><strong>{Math.round(attempt.score)} %</strong><small className="muted">{attempt.correct_count ?? "-"}/{attempt.total_questions ?? "-"}</small></div>)}</div>}</div></>}</section>
      </>}
    </RequireUser>
  </>;
}

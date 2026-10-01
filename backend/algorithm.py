"""
Algorithmes "métier" de l'assistant de révisions.

1. generate_plan()           -> planning heuristique, règle "faiblesses d'abord"
2. compute_retention()       -> spaced repetition light (SM-2 simplifié) [BONUS]
3. recommend_resources()     -> recommandation par mots-clés (règles)   [BONUS]
4. recommend_resources_ai()  -> recommandation par IA (Gemini)          [BONUS]
"""
import datetime
import json
import logging
import os
import re
from typing import List, Dict, Optional
from urllib.parse import quote_plus

DAYS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
logger = logging.getLogger(__name__)


class AIConfigurationError(Exception):
    """La configuration necessaire a l'appel du fournisseur IA manque."""


class AIGenerationError(Exception):
    """Le fournisseur IA a echoue ou a renvoye un contenu inexploitable."""


def _safe_provider_error(error: Exception, api_key: str) -> str:
    """Conserve le diagnostic Gemini sans risquer de journaliser une cle API."""
    message = str(error).replace(api_key, "[REDACTED]")
    return re.sub(
        r"(?i)(api[_ -]?key[=:]\s*)[^\s,;]+",
        r"\1[REDACTED]",
        message,
    )


def _extract_json(text: str, expected_type: type) -> object:
    """Extrait un objet ou tableau JSON, y compris si le modele ajoute du Markdown."""
    opening, closing = ("{", "}") if expected_type is dict else ("[", "]")
    start = text.find(opening)
    end = text.rfind(closing)
    if start < 0 or end < start:
        raise AIGenerationError("La reponse IA n'est pas au format JSON attendu.")
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise AIGenerationError("La reponse IA contient un JSON invalide.") from exc
    if not isinstance(payload, expected_type):
        raise AIGenerationError("La reponse IA n'a pas la structure attendue.")
    return payload


def _generate_json(prompt: str, max_tokens: int, expected_type: type) -> object:
    """Appelle Gemini sans jamais transmettre la cle hors du backend."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise AIConfigurationError("GEMINI_API_KEY n'est pas configuree.")
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                max_output_tokens=max_tokens,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(
                    disable=True
                ),
            ),
        )
        response_text = response.text
        if not response_text:
            raise ValueError("Gemini returned no usable text.")
    except Exception as exc:
        logger.error(
            "Gemini generation failed for model %s (%s): %s",
            model,
            type(exc).__name__,
            _safe_provider_error(exc, api_key),
        )
        raise AIGenerationError("Le service IA est temporairement indisponible.") from exc

    return _extract_json(response_text, expected_type)


def generate_course_ai(
    subject: str,
    level: str,
    language: str,
    desired_length: int,
    objectives: List[str],
    requested_chapters: List[str],
) -> Dict:
    """Genere un cours structure, pret a etre valide puis persiste par l'API."""
    chapters_hint = ", ".join(requested_chapters) or "choisis des chapitres pedagogiques adaptes"
    prompt = f"""Genere un cours de revision en {language}.
Sujet : {subject}
Niveau : {level}
Longueur cible : environ {desired_length} mots.
Objectifs : {json.dumps(objectives, ensure_ascii=False)}
Chapitres souhaites : {chapters_hint}

Reponds UNIQUEMENT avec un objet JSON valide de cette forme :
{{
  "chapters": [{{"title": "...", "explanation": "...", "examples": ["..."]}}],
  "content": "cours complet structure avec explications et exemples",
  "summary": "resume concis"
}}
Les explications, exemples et resume doivent etre en {language}."""
    return _generate_json(prompt, max_tokens=min(12_000, desired_length * 3), expected_type=dict)


def generate_quiz_ai(
    course_content: str,
    language: str,
    question_count: int,
    difficulty: str,
    level: int = 1,
    avoided_questions: Optional[List[str]] = None,
    review_notions: Optional[List[Dict[str, str]]] = None,
) -> List[Dict]:
    """Genere un QCM avec exactement quatre choix et une seule bonne reponse."""
    if level == 1:
        level_guidance = "definitions, unites, formules de base et reconnaissance des notions"
    elif level == 2:
        level_guidance = "applications directes de formules et exercices guides"
    else:
        level_guidance = "calculs a plusieurs etapes, cas pratiques et pieges frequents"
    avoided = json.dumps((avoided_questions or [])[-100:], ensure_ascii=False)
    recalls = review_notions or []
    recall_instruction = ""
    if recalls:
        recall_instruction = f"""
NOTIONS A CONSOLIDER : {json.dumps(recalls[:2], ensure_ascii=False)}
Integre exactement {min(len(recalls), 2)} question(s) de rappel sur ces notions. Reformule-les completement : ne reutilise jamais le texte d'une ancienne question. Conserve exactement la notion_key fournie pour chaque question de rappel.
"""
    prompt = f"""A partir du cours suivant, cree exactement {question_count} questions QCM de niveau {difficulty}, en {language}.
NIVEAU DE PROGRESSION : {level}. Privilegie : {level_guidance}.
Questions deja posees a cet etudiant, a ne jamais reformuler ni reutiliser : {avoided}
{recall_instruction}

COURS :
{course_content}

Reponds UNIQUEMENT avec un tableau JSON. Chaque objet doit avoir exactement cette forme :
{{
  "question": "...",
  "choices": ["choix 1", "choix 2", "choix 3", "choix 4"],
  "correct_index": 0,
  "explanation": "explication de la bonne reponse",
  "notion_key": "identifiant-court-stable-de-la-notion"
}}
Il doit y avoir exactement quatre choix distincts et un seul choix correct par question.
Les questions du tableau doivent etre toutes differentes entre elles. notion_key doit etre en minuscules, sans accents ni espaces, avec des tirets."""
    return _generate_json(prompt, max_tokens=max(1_000, question_count * 400), expected_type=list)


# ---------------------------------------------------------------------------
# 1. Génération du planning
# ---------------------------------------------------------------------------
def _weakness_score(avg_score: Optional[float]) -> float:
    """Score moyen (0-100, haut = bon) -> faiblesse (haut = à prioriser).
    Un module jamais évalué est considéré comme prioritaire."""
    if avg_score is None:
        return 100.0
    return max(0.0, 100.0 - avg_score)


def generate_plan(
    modules: List[Dict],
    total_hours_per_week: float,
    days_per_week: int = 6,
) -> List[Dict]:
    """
    Règle heuristique "faiblesses d'abord" :
      - chaque module reçoit d'abord son objectif hebdo minimal
      - le temps restant est distribué proportionnellement à la faiblesse
      - le total est réparti sur les jours disponibles, modules faibles d'abord

    `modules` : liste de dicts {id, name, weekly_objective_hours, avg_score}
    """
    if not modules:
        return []

    days_per_week = max(1, min(7, days_per_week))
    days = DAYS[:days_per_week]

    base_alloc = {m["id"]: m["weekly_objective_hours"] for m in modules}
    base_total = sum(base_alloc.values())
    remaining = max(0.0, total_hours_per_week - base_total)

    weaknesses = {m["id"]: _weakness_score(m.get("avg_score")) for m in modules}
    weight_sum = sum(weaknesses.values()) or 1.0

    total_alloc = {
        m["id"]: round(
            base_alloc[m["id"]] + remaining * (weaknesses[m["id"]] / weight_sum), 2
        )
        for m in modules
    }

    modules_sorted = sorted(modules, key=lambda m: weaknesses[m["id"]], reverse=True)

    slots: List[Dict] = []
    day_index = 0
    session_length = 1.0

    for m in modules_sorted:
        hours_left = total_alloc[m["id"]]
        weakness = weaknesses[m["id"]]
        if weakness >= 60:
            priority = "Priorité haute (faiblesse)"
        elif weakness >= 30:
            priority = "Priorité moyenne"
        else:
            priority = "Priorité basse (consolidation)"

        while hours_left > 0.01:
            duration = min(session_length, hours_left)
            slots.append(
                {
                    "day": days[day_index % len(days)],
                    "module_id": m["id"],
                    "module_name": m["name"],
                    "hours": round(duration, 2),
                    "priority": priority,
                }
            )
            hours_left -= duration
            day_index += 1

    day_order = {d: i for i, d in enumerate(days)}
    slots.sort(key=lambda s: day_order[s["day"]])
    return slots


# ---------------------------------------------------------------------------
# 2. Courbe de rétention (spaced repetition light)
# ---------------------------------------------------------------------------
def compute_retention(attempts: List[Dict]) -> Dict:
    """Rejoue l'historique avec la variante SM-2 utilisee par la retention."""
    if not attempts:
        return {
            "last_score": None,
            "interval_days": 1,
            "next_review": None,
            "ef": 2.5,
            "reps": 0,
            "days_since": None,
            "retention": None,
            "overdue_days": 0,
        }

    attempts_sorted = sorted(attempts, key=lambda a: a["date"])
    ef = 2.5
    reps = 0
    interval = 1
    for a in attempts_sorted:
        quality = round(float(a["score"]) / 100 * 5)
        if quality < 3:
            reps = 0
            interval = 1
        else:
            reps += 1
            if reps == 1:
                interval = 1
            elif reps == 2:
                interval = 3
            else:
                interval = max(1, round(interval * ef))
        misses = 5 - quality
        ef = max(1.3, ef + 0.1 - misses * (0.08 + misses * 0.02))

    last_date = attempts_sorted[-1]["date"]
    last_score = attempts_sorted[-1]["score"]
    if hasattr(last_date, "date"):
        last_date = last_date.date()
    today = datetime.date.today()
    days_since = max(0, (today - last_date).days)
    next_review = last_date + datetime.timedelta(days=interval)

    return {
        "last_score": last_score,
        "interval_days": interval,
        "next_review": next_review,
        "ef": ef,
        "reps": reps,
        "days_since": days_since,
        "retention": 0.9 ** (days_since / interval),
        "overdue_days": max(0, days_since - interval),
    }


# ---------------------------------------------------------------------------
# 3. Ressources — version règles (secours, ne nécessite pas internet)
# ---------------------------------------------------------------------------
_RESOURCE_KB = {
    "math": [
        {"title": "Exercices corrigés - Exo7", "url": "https://exo7.emath.fr/", "type": "site"},
        {"title": "Khan Academy - Mathématiques", "url": "https://fr.khanacademy.org/math", "type": "cours"},
    ],
    "physique": [
        {"title": "Physique - Khan Academy", "url": "https://fr.khanacademy.org/science/physics", "type": "cours"},
        {"title": "Fiches de physique - Prépabac", "url": "https://www.prepabac.net/", "type": "fiches"},
    ],
    "chimie": [
        {"title": "Chimie - Khan Academy", "url": "https://fr.khanacademy.org/science/chemistry", "type": "cours"},
    ],
    "info": [
        {"title": "OpenClassrooms - Programmation", "url": "https://openclassrooms.com/fr/courses", "type": "cours"},
        {"title": "Documentation Python officielle", "url": "https://docs.python.org/fr/3/", "type": "documentation"},
    ],
    "informatique": [
        {"title": "OpenClassrooms - Programmation", "url": "https://openclassrooms.com/fr/courses", "type": "cours"},
    ],
    "anglais": [
        {"title": "BBC Learning English", "url": "https://www.bbc.co.uk/learningenglish", "type": "site"},
    ],
    "langue": [
        {"title": "Duolingo", "url": "https://www.duolingo.com/", "type": "application"},
    ],
    "histoire": [
        {"title": "Herodote.net", "url": "https://www.herodote.net/", "type": "site"},
    ],
    "bio": [
        {"title": "Biologie - Khan Academy", "url": "https://fr.khanacademy.org/science/biology", "type": "cours"},
    ],
    "economie": [
        {"title": "Melchior - ressources en économie", "url": "https://www.melchior.fr/", "type": "site"},
    ],
}

_DEFAULT_RESOURCES = [
    {"title": "Recherche Google Scholar sur le sujet", "url": "https://scholar.google.com/", "type": "recherche"},
    {"title": "Wikipédia - point de départ général", "url": "https://fr.wikipedia.org/", "type": "encyclopédie"},
]


def recommend_resources(module_name: str, course: str = "") -> List[Dict]:
    """Recommandation par mots-clés trouvés dans le nom du module / du cours."""
    text = f"{module_name} {course}".lower()
    results: List[Dict] = []
    for keyword, resources in _RESOURCE_KB.items():
        if keyword in text:
            results.extend(resources)
    return results or _DEFAULT_RESOURCES


# ---------------------------------------------------------------------------
# 4. Ressources — version IA (Gemini)
# ---------------------------------------------------------------------------
def recommend_resources_ai(
    module_name: str, course: str = "", avg_score: Optional[float] = None
) -> List[Dict]:
    """
    Demande à Gemini des ressources adaptées au module ET au niveau de
    l'étudiant (score moyen des quiz).

    Pour éviter les liens inventés ou morts, l'IA ne fournit que des titres
    et des requêtes de recherche ; les liens (YouTube / Google) sont
    construits ici et fonctionnent donc toujours.

    Nécessite : pip install google-genai + variable GEMINI_API_KEY.
    Lève une exception en cas de problème (le appelant gère le fallback).
    """
    if avg_score is None:
        niveau = "niveau inconnu (pas encore évalué)"
    elif avg_score < 50:
        niveau = f"faible (score {avg_score:.0f}%) : privilégie les bases"
    elif avg_score < 80:
        niveau = f"moyen (score {avg_score:.0f}%) : consolidation"
    else:
        niveau = f"bon (score {avg_score:.0f}%) : approfondissement"

    prompt = f"""Un étudiant révise le module « {module_name} » (cours : {course or "non précisé"}).
Son niveau actuel : {niveau}.
Propose 4 ressources de révision adaptées à ce niveau, en français si possible.
Réponds UNIQUEMENT par un tableau JSON, sans texte autour, de la forme :
[{{"title": "...", "type": "video" ou "cours" ou "exercices" ou "pdf", "query": "requête de recherche précise"}}]"""

    items = _generate_json(prompt, max_tokens=800, expected_type=list)

    results: List[Dict] = []
    for it in items:
        q = quote_plus(it["query"])
        kind = it.get("type", "cours")
        if kind == "video":
            url = f"https://www.youtube.com/results?search_query={q}"
        elif kind == "pdf":
            url = f"https://www.google.com/search?q={q}+filetype%3Apdf"
        else:
            url = f"https://www.google.com/search?q={q}"
        results.append({"title": it["title"], "url": url, "type": kind})
    return results

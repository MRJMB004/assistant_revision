# Réviser — Assistant de révisions personnalisé

Plan de révision adaptatif pour un semestre : crée tes modules, passe des
quiz diagnostics, et obtiens un planning hebdomadaire généré automatiquement
selon la règle **« faiblesses d'abord »**.

## Fonctionnalités

### MVP
- Création de modules/cours avec objectif hebdomadaire (heures)
- Quiz diagnostic par module (QCM), score et diagnostic automatiques
- Génération de planning : algorithme heuristique qui priorise les modules
  où le score de quiz est le plus faible, tout en respectant l'objectif
  hebdomadaire minimal de chaque module
- Notifications e-mail **simulées** (récapitulatif du planning, stocké et
  consultable dans l'app — voir `backend/main.py` pour brancher un envoi
  SMTP réel)

### Bonus
- **Recommandation de ressources** par mots-clés (règles simples sur le
  nom/cours du module — voir `backend/algorithm.py::recommend_resources`)
- **Courbe de rétention** (spaced repetition light, inspirée de SM-2) :
  calcule un intervalle avant la prochaine révision en fonction du dernier
  score obtenu

## Stack

- **Backend** : FastAPI + SQLAlchemy + SQLite (`backend/`)
- **Frontend** : React 19 + Vite (`frontend/`), graphiques avec Chart.js
  (`react-chartjs-2`) et icônes `lucide-react`. Un seul état global léger
  (contexte React) : pas de routeur ni de librairie d'état supplémentaire.

## Lancer le projet

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate          # Windows : venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

L'API est alors disponible sur `http://localhost:8000` (documentation
interactive sur `http://localhost:8000/docs`).

### 2. Frontend

Dans un second terminal (Node.js 20+ requis) :

```bash
cd frontend
npm install
npm run dev
```

Puis ouvre `http://localhost:5173` dans ton navigateur.

> Le frontend appelle l'API sur `http://localhost:8000` par défaut. Pour
> changer l'adresse, copie `frontend/.env.example` en `frontend/.env` et
> modifie `VITE_API_BASE`.

Build de production : `npm run build` (sortie dans `frontend/dist/`, à servir
avec n'importe quel serveur statique ; `npm run preview` pour tester).

## Structure du projet

```
assistant-revisions/
├── backend/
│   ├── main.py          # Routes FastAPI
│   ├── models.py         # Modèles SQLAlchemy (User, Module, Quiz, Plan, Notification)
│   ├── schemas.py         # Schémas Pydantic
│   ├── algorithm.py       # Génération du planning, rétention, ressources
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── .env.example
│   └── src/
│       ├── main.jsx          # Point d'entrée
│       ├── App.jsx           # Navigation par onglets (synchronisée avec l'URL #)
│       ├── AppContext.jsx    # Profil courant, modules, thème, toasts, statut API
│       ├── api.js            # Client fetch + gestion des erreurs FastAPI
│       ├── hooks.js          # useRetention
│       ├── styles.css
│       ├── components/       # Sidebar, composants UI partagés
│       └── pages/            # Dashboard, Setup, Modules, Quiz, Plan,
│                             # Resources, Retention, Notifications
└── README.md
```

## Modèle de données (backlog "Modèles: User, Module, Quiz, Score, Plan")

| Table          | Rôle                                                       |
|----------------|--------------------------------------------------------------|
| `users`        | Profil de l'étudiant                                          |
| `modules`      | Cours/modules avec objectif hebdo                             |
| `quiz_questions` | Questions QCM rattachées à un module                        |
| `quiz_attempts`  | Historique des scores (sert au calcul de faiblesse et de rétention) |
| `plans`        | Plannings générés (créneaux par jour)                         |
| `notifications`  | Historique des notifications envoyées (simulées)             |

## Algorithme de planning (règle heuristique)

1. Chaque module reçoit d'abord son objectif hebdomadaire minimal.
2. Le temps restant disponible est distribué proportionnellement à la
   **faiblesse** de chaque module (`100 - score moyen des quiz`; un module
   jamais évalué est traité comme prioritaire).
3. Le total est découpé en séances d'environ 1h et réparti sur les jours
   disponibles, en plaçant les modules les plus faibles en premier.

Voir `backend/algorithm.py::generate_plan` pour l'implémentation complète et
commentée.

## Jalons suggérés (backlog)

- **S1** : modèles de données + auth basique (fait dans ce prototype : création
  de profil sans mot de passe, à durcir si besoin)
- **S2** : quiz + génération de planning (fait)
- **S3** : dashboard (fait — planning hebdomadaire visuel)
- **S4** : polissage + documentation (ce README, styles, gestion d'erreurs)

## Pistes d'évolution

- Authentification réelle (mot de passe/JWT) au lieu d'un simple profil
- Envoi SMTP réel pour les notifications (le point d'ancrage est déjà
  présent dans `backend/main.py::send_notification`)
- Remplacer la base de ressources par mots-clés par des embeddings pour des
  recommandations "ressources proches" plus fines
- Migration SQLite → PostgreSQL pour la production

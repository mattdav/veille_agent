# veille_agent

Agent de veille technologique hebdomadaire autonome. Il collecte des articles
depuis des flux RSS, arXiv et GitHub, les filtre par pertinence thématique,
les analyse via l'API Claude, puis génère un briefing HTML et Markdown
personnalisé — livrable par email ou écrit sur disque.

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](https://choosealicense.com/licenses/mit/)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Lint](https://github.com/mattdav/veille_agent/actions/workflows/lint.yml/badge.svg)](https://github.com/mattdav/veille_agent/actions/workflows/lint.yml)
[![Tests](https://github.com/mattdav/veille_agent/actions/workflows/test.yml/badge.svg)](https://github.com/mattdav/veille_agent/actions/workflows/test.yml)

---

## Sommaire

- [Pipeline](#pipeline)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Personnalisation du profil](#personnalisation-du-profil--profileyaml)
  - [Variables d'environnement](#variables-denvironnement)
- [Utilisation](#utilisation)
  - [Commandes invoke](#commandes-invoke)
  - [Options CLI](#options-cli)
- [Sorties](#sorties)
- [Envoi par email (Gmail)](#envoi-par-email-gmail)
- [Intégration continue](#intégration-continue)
- [Étendre l'agent](#étendre-lagent)

---

## Pipeline

L'agent exécute cinq étapes séquentielles à chaque lancement :

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Collecte        RSS (feedparser) + arXiv + GitHub API        │
│                          ↓ RawItem[]                             │
│  2. Déduplication   SQLite — exclut les URLs déjà traités        │
│                          ↓ RawItem[] (nouveaux)                  │
│  3. Pré-filtrage    Regex mot-clé sur titre + résumé (seuil 0.08)│
│                          ↓ RawItem[] (pertinents)                │
│  4. Extraction      Jina Reader (r.jina.ai) si résumé < 100 cars │
│                          ↓ RawItem[] + dict{uid: fulltext}        │
│  5. Analyse Claude  Batch ≤ 20 items → JSON scoré (0-10)         │
│                          ↓ ScoredItem[]                          │
│     Génération      briefing.html + briefing.md                  │
│     (opt.) Email    SMTP Gmail avec STARTTLS                      │
└─────────────────────────────────────────────────────────────────┘
```

Chaque collecteur absorbe ses erreurs réseau et retourne `[]` en cas d'échec :
le pipeline continue même si une source est indisponible. Seules les erreurs
Claude API sont propagées (étape critique).

---

## Prérequis

| Outil | Version | Rôle |
|-------|---------|------|
| Python | ≥ 3.13 | Interpréteur |
| [uv](https://github.com/astral-sh/uv) | dernière | Gestionnaire de paquets et environnements virtuels |
| Clé API Anthropic | — | Accès à Claude pour l'analyse |

---

## Installation

```bash
# 1. Cloner le dépôt
git clone https://github.com/mattdav/veille_agent.git
cd veille_agent

# 2. Installer les dépendances (runtime + dev + lint)
uv sync --extra dev --extra lint

# 3. Copier et remplir les variables d'environnement
cp .env.example .env
# Éditer .env avec votre ANTHROPIC_API_KEY (voir section Variables d'environnement)

# 4. Vérifier l'installation
inv lint
inv test
```

---

## Configuration

Toute valeur personnalisable — thématiques, sources, seuils, limites, modèle
Claude — vit dans un seul fichier déclaratif. `.env` est réservé aux secrets.

### Personnalisation du profil — `profile.yaml`

**`src/veille_agent/config/profile.yaml`** est le seul fichier à éditer pour
adapter l'agent à vos besoins. Aucune modification du code Python n'est
requise.

```yaml
# Mots-clés utilisés par le pré-filtre ET injectés dans le prompt Claude.
topics:
  - dbt
  - data engineering
  - python
  - LLM
  - agents IA

# Description narrative de votre situation, vos projets en cours et vos
# objectifs. Elle est injectée telle quelle dans le prompt d'analyse Claude.
context: |
  Développeur Python senior spécialisé en data engineering et IA.
  Projets en cours : migration Alteryx → dbt, agents IA autonomes…
  Objectif : trouver des outils directement applicables au travail
  quotidien ou réalisables en POC en moins d'une journée.

# Critères de scoring pour Claude (0-10), en langage naturel.
scoring:
  high:   "directement utilisable cette semaine dans un projet en cours"
  medium: "applicable à moyen terme ou ouvre une piste de POC intéressante"
  low:    "intéressant mais trop éloigné des projets actuels"
  # Seuil unique d'inclusion dans le briefing ET de persistance recap.
  threshold: 6.0

# Sources à surveiller
rss_feeds:
  - name: "Hacker News Best"
    url: "https://hnrss.org/best"
rss_since_days: 7
arxiv_categories: [cs.AI, cs.LG, cs.SE]
github_topics: [llm, data-engineering, python, agents]
youtube_channels: ["@PyCon"]
youtube_max_per_channel: 3

# Paramètres techniques du pipeline
claude_batch_size: 20                   # articles par appel Claude (max recommandé : 20)
deepdive_threshold: 9.0                 # score déclenchant un deepdive
max_items_per_briefing: 20              # plafond d'articles dans le briefing
recap_since_weeks: 4                    # fenêtre par défaut du recap mensuel
```

**Ajouter un flux RSS :** ajouter une entrée `{name, url}` sous `rss_feeds`
dans `profile.yaml` — aucun redémarrage ni modification de code requis.

**Changer le modèle Claude :** éditer `CLAUDE_MODEL` dans `.env`.

### Variables d'environnement

Copiez `.env.example` en `.env` à la racine du projet et renseignez les
variables. Le fichier `.env` est chargé automatiquement au démarrage via
`python-dotenv` et ne doit jamais être commité.

| Variable | Obligatoire | Description |
|----------|-------------|-------------|
| `ANTHROPIC_API_KEY` | **Oui** | Clé API Anthropic — obtenir sur [console.anthropic.com](https://console.anthropic.com/) |
| `CLAUDE_MODEL` | **Oui** | Modèle Claude pour l'analyse et les deepdives (ex: `claude-sonnet-4-6`) |
| `GMAIL_FROM` | Non | Adresse Gmail expéditrice (ex: `vous@gmail.com`) |
| `GMAIL_APP_PASSWORD` | Non | Mot de passe d'application Gmail — 16 caractères, sans espaces |
| `GITHUB_TOKEN` | Non | Token GitHub — augmente la limite de l'API de 60 à 5 000 req/h (utile si > 10 topics) |
| `PUBLISH_PATH` | Non | Répertoire secondaire de copie du briefing markdown (ex: vault Obsidian) |

Exemple de fichier `.env` :
```dotenv
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-6
GMAIL_FROM=vous@gmail.com
GMAIL_APP_PASSWORD=abcdabcdabcdabcd
GITHUB_TOKEN=ghp_...
PUBLISH_PATH=/publish
```

---

## Utilisation

### Options CLI

Le point d'entrée accepte trois options :

```bash
# Exécution standard — génère les briefings dans data/briefings/
python -m veille_agent

# Ou via le script installé
veille_agent

# Envoyer le briefing HTML par email après génération
python -m veille_agent --email vous@gmail.com

# Dry-run : collecte et filtrage uniquement, sans appeler Claude ni SQLite.
# Utile pour tester la configuration des sources sans consommer de tokens.
python -m veille_agent --dry-run

# Écrire les briefings dans un dossier spécifique
python -m veille_agent --output-dir /chemin/vers/dossier

# Copier le briefing markdown vers un second répertoire (ex : vault Obsidian)
python -m veille_agent --publish-path /chemin/vers/vault

# Combinaison
python -m veille_agent --email vous@gmail.com --output-dir ./sorties
```

**Sortie console d'une exécution normale :**
```
1/5 — Collecte des sources...
    87 items bruts collectés
2/5 — Déduplication...
    34 nouveaux items
3/5 — Pré-filtrage thématique...
    21 items après filtre
4/5 — Extraction full-text (Jina Reader)...
    5 full-texts extraits
5/5 — Analyse Claude (batch)...
    Batch 1/2 analysé
    Batch 2/2 analysé
Briefing sauvegardé : data/briefings/2025-W42.*
```

---

## Sorties

L'agent génère deux fichiers dans `data/briefings/` (nommage `YYYY-WNN`) :

### `YYYY-WNN.html`

Briefing autonome avec CSS intégré (aucune dépendance externe — compatible
email et consultation hors ligne). Il contient :

- En-tête avec le nombre d'articles retenus et d'idées de POC
- Section **Idées de POC** : les 5 premières idées de POC de la semaine
- Section **Articles retenus** : chaque article avec son score (surligné
  en jaune si ≥ 8), sa source, ses tags, le résumé en français,
  la justification de pertinence et l'idée de POC associée

### `YYYY-WNN.md`

Briefing Markdown compatible Obsidian / Notion. Structure :

```markdown
# Veille tech 2025-W42

## Idées de POC
- **dbt** — Implémenter le pattern X dans le pipeline Y

## Articles
### [Titre de l'article](https://url) `8/10`
*Hacker News Best · #dbt #python*

Résumé en 2-3 phrases en français…

> POC : Idée de POC en une phrase.
```

### Déduplication SQLite

Les URLs collectées sont stockées dans `data/watch.db` (table `seen`).
Les articles déjà traités lors des semaines précédentes sont automatiquement
exclus. Pour forcer une re-analyse complète :

```bash
python -c "
import sqlite3
conn = sqlite3.connect('src/veille_agent/data/watch.db')
conn.execute('DELETE FROM seen')
conn.commit()
"
```

---

## Envoi par email (Gmail)

L'envoi utilise SMTP Gmail avec STARTTLS. Un **mot de passe d'application**
(différent de votre mot de passe Gmail) est obligatoire.

**Étapes de configuration :**

1. Activer la validation en deux étapes sur votre compte Google
   ([myaccount.google.com/security](https://myaccount.google.com/security))
2. Générer un mot de passe d'application :
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   — choisir "Autre" comme application
3. Copier les 16 caractères (sans espaces) dans `GMAIL_APP_PASSWORD`
4. Renseigner `GMAIL_FROM` avec votre adresse Gmail

```bash
# Test d'envoi
python -m veille_agent --email vous@gmail.com --dry-run
# dry-run évite d'appeler Claude, mais l'email ne sera pas envoyé car il n'y
# a pas de briefing généré en dry-run — utilisez une exécution normale :
python -m veille_agent --email vous@gmail.com
```

---

## Intégration continue

Trois workflows GitHub Actions s'exécutent à chaque push :

| Workflow | Fichier | Ce qu'il vérifie |
|----------|---------|-----------------|
| **Lint** | `.github/workflows/lint.yml` | `ruff check` + `ruff format --check` + `mypy --strict` |
| **Tests** | `.github/workflows/test.yml` | `pytest` avec couverture ≥ 80 % |
| **Docs** | `.github/workflows/docs.yml` | Build de la documentation Sphinx |

---

## Étendre l'agent

### Ajouter une source de collecte

1. Créer une fonction `collect_xxx() -> list[RawItem]` dans
   `src/veille_agent/bin/collector.py` — elle doit absorber ses propres
   erreurs et retourner `[]` en cas d'échec
2. L'appeler dans `__main__.py::run()` à l'étape de collecte

```python
# collector.py
def collect_mon_flux(url: str) -> list[RawItem]:
    """Collecte depuis ma source custom."""
    try:
        ...
        return [RawItem(title=..., url=..., source="MaSource")]
    except Exception:
        return []

# __main__.py — dans run()
items += collect_mon_flux(profile.mon_flux_url)
```

Si l'URL doit être personnalisable sans toucher au code, ajouter le champ
correspondant (`mon_flux_url`) à `UserProfile` (`profile.py`) et à
`profile.yaml`.

### Ajouter un champ au briefing

Modifier simultanément (les quatre sont couplés) :

1. `_build_prompt()` dans `analyst.py` — ajouter le champ à la spécification JSON
2. Parsing dans `analyze_batch()` dans `analyst.py` — extraire le champ du JSON
3. `ScoredItem` dans `analyst.py` — déclarer le nouveau champ
4. `generate_html_briefing()` et `generate_markdown_briefing()` dans `briefing.py`

### Modifier les thématiques sans toucher au code

Éditer uniquement `src/veille_agent/config/profile.yaml` — la section
`topics` est lue au démarrage et injectée dans le pré-filtre et le prompt
Claude. Aucun redéploiement ni redémarrage nécessaire.

---

## Auteur

[@mattdav](https://github.com/mattdav)

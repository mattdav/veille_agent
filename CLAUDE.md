# CLAUDE.md — Agent de veille technologique hebdomadaire

## Vue d'ensemble du projet

Agent Python autonome qui collecte, filtre et analyse des sources technologiques
(RSS, arXiv, GitHub) chaque semaine, puis génère un briefing HTML/Markdown
personnalisé via l'API Claude.

**Stack principale** : Python 3.13, `anthropic`, `feedparser`, `httpx`,
`pyyaml`, `python-dotenv`, `sqlite3`
**Gestionnaire de paquets** : `uv`
**Automatisation** : `invoke` (`inv lint`, `inv test`, `inv run`…)
**Qualité** : `ruff` (lint + format), `mypy` (strict), `pytest` (doctest + coverage)
**Exécution** : `python -m veille_agent` ou `veille_agent` (script installé)
**Modèle Claude** : `claude-sonnet-4-20250514`
**Infrastructure** : Docker multi-arch (amd64 + arm64), Raspberry Pi, Portainer
**Registry** : GitHub Container Registry (`ghcr.io`)
**Planification** : GitHub Actions cron (lundi 6h UTC) → SSH → Raspberry Pi

---

## Structure du projet

```
veille_agent/
├── CLAUDE.md                          # ce fichier
├── tasks.py                           # tâches invoke (lint, test, run…)
├── pyproject.toml                     # config build, dépendances, outils
├── uv.lock
├── .python-version                    # 3.13
├── Dockerfile                         # image multi-arch amd64 + arm64
├── docker-compose.yml                 # définition du service conteneur
├── .dockerignore                      # exclusions du contexte Docker build
├── .env.example                       # variables d'environnement à copier en .env
├── .env                               # NE PAS COMMITER — gitignore
├── config.cfg.example
├── .github/
│   └── workflows/
│       ├── lint.yml                   # ruff + mypy sur chaque push
│       ├── test.yml                   # pytest sur chaque push
│       └── weekly-watch.yml           # build Docker + deploy Raspberry Pi (lundi 6h)
├── src/
│   └── veille_agent/
│       ├── __init__.py                # métadonnées du package
│       ├── __main__.py                # orchestrateur + CLI (point d'entrée)
│       ├── py.typed                   # marqueur PEP 561
│       ├── bin/                       # modules métier
│       │   ├── __init__.py
│       │   ├── config.py              # WatchConfig (paramètres techniques)
│       │   ├── profile.py             # UserProfile + load_profile()
│       │   ├── collector.py           # collecte RSS / arXiv / GitHub
│       │   ├── filter.py              # pré-filtrage par mots-clés
│       │   ├── reader.py              # extraction full-text via Jina Reader
│       │   ├── analyst.py             # analyse batch via Claude API
│       │   ├── briefing.py            # génération HTML + Markdown
│       │   └── mailer.py              # envoi Gmail SMTP
│       ├── config/                    # dossier runtime (gitignore sauf profile.yaml)
│       │   └── profile.yaml           # ÉDITER ICI — profil utilisateur déclaratif
│       ├── data/                      # dossier runtime (gitignore)
│       │   ├── watch.db               # SQLite déduplication
│       │   └── briefings/             # livrables générés
│       │       ├── 2025-W42.html
│       │       └── 2025-W42.md
│       └── log/                       # dossier runtime (gitignore)
│           └── app.log
└── tests/
    ├── __init__.py
    ├── conftest.py                    # fixtures pytest
    └── unit/                          # tests unitaires
```

Les dossiers `data/` et `log/` sont gitignorés. `config/` est gitignore
**sauf** `profile.yaml` qui est versionné (il ne contient pas de secrets).

---

## Personnalisation du profil — fichier déclaratif

**`src/veille_agent/config/profile.yaml`** est le seul fichier à éditer pour
personnaliser le comportement de l'agent. Il contient :

- `topics` : mots-clés utilisés pour le pré-filtre ET injectés dans le prompt
- `context` : description narrative du développeur, ses projets et objectifs —
  injectée telle quelle dans le prompt Claude
- `scoring.high/medium/low` : définitions des niveaux de score en langage
  naturel — permettent à Claude de calibrer ses notes
- `scoring.threshold` : seuil d'inclusion dans le briefing (défaut 6.0)

**Règle** : tout ce qui relève du "qui je suis et ce qui m'intéresse" va dans
`profile.yaml`. Tout ce qui relève du "comment le programme fonctionne"
(sources, batch size, modèle) reste dans `WatchConfig`.

---

## Architecture des modules

### `__main__.py` — Orchestrateur + CLI

Point d'entrée unique. Charge `.env` via `load_dotenv()` au démarrage.

Fonctions :
- `_get_package_dir(folder_name)` : résout les chemins runtime via
  `importlib.resources`
- `_setup_logging(log_path)` : configure le logger dans `log/app.log`
- `run(config, profile, db_path, output_dir, email_to, dry_run)` : pipeline
  complet, retourne la liste des `ScoredItem`
- `main()` : parse les arguments CLI, charge `WatchConfig` et `UserProfile`,
  appelle `run()`

**Arguments CLI** :
```
--email ADRESSE     Envoyer le briefing par email via Gmail
--dry-run           Collecter et filtrer sans appeler Claude ni écrire en base
--output-dir PATH   Dossier de sortie (défaut : data/briefings/)
```

**Règle** : `__main__.py` n'orchestre que — toute logique métier va dans `bin/`.

---

### `bin/config.py` — `WatchConfig`

Dataclass des paramètres **techniques** de l'agent (sources, batch size,
modèle). Ne contient rien de propre au profil utilisateur.

Champs :
- `rss_feeds` : liste de `{"name": str, "url": str}`
- `arxiv_categories`, `github_topics` : sources à surveiller
- `min_relevance_score` : seuil de briefing (lu depuis `profile.threshold` en
  pratique — `WatchConfig` garde la valeur par défaut comme fallback)
- `claude_batch_size` : items par appel Claude (max recommandé : 20)
- `claude_model` : identifiant du modèle

**Règle** : ne jamais hard-coder de valeurs dans les autres modules.

---

### `bin/profile.py` — `UserProfile` + `load_profile()`

- `UserProfile` : dataclass avec `topics`, `context`, `scoring_*`, `threshold`
- `load_profile(path: Path) -> UserProfile` : charge `profile.yaml` via
  `yaml.safe_load()`

**Règle** : modifier `profile.yaml` ne nécessite pas de toucher au code Python.

---

### `bin/collector.py` — Collecte multi-sources

Fonctions indépendantes retournant `list[RawItem]` :
- `collect_rss(feeds, since_days=7)`
- `collect_arxiv(categories, max_results=30)`
- `collect_github_trending(topics)` — API publique GitHub, 60 req/h sans token
- `deduplicate(items, db_path)` — filtre via table `seen` dans SQLite

`RawItem` : dataclass avec `uid = md5(url)`.

**Règle** : chaque collecteur absorbe ses propres erreurs réseau et retourne
`[]` en cas d'échec — jamais de propagation d'exception.

**Ajouter une source** : créer `collect_xxx() -> list[RawItem]` dans
`collector.py`, l'appeler dans `__main__.py::run()`.

---

### `bin/filter.py` — Pré-filtrage

- `keyword_score(item, topics) -> float` : regex `\bword\b` sur titre + résumé
- `pre_filter(items, topics, threshold=0.08)` : élimine le bruit avant Claude

Seuil intentionnellement bas (0.08) — Claude affine ensuite.

---

### `bin/reader.py` — Extraction full-text

- `fetch_fulltext(url, max_chars=3000) -> str`
- Préfixe `https://r.jina.ai/` — API publique, sans clé, ~60 req/min
- Appelé uniquement si `len(item.summary) < 100`
- Retourne `""` en cas d'erreur (dégradation gracieuse)

---

### `bin/analyst.py` — Cœur IA

- `analyze_batch(items, profile, fulltext, model) -> list[ScoredItem]`
- `_build_prompt(articles_payload, profile) -> str` : construit le prompt en
  injectant `profile.context`, `profile.topics` et les critères de scoring
- Client Anthropic : singleton lazy `_get_client()`
- System prompt dans `ANALYST_SYSTEM` (constante module-level)

**Format JSON attendu de Claude** — couplé avec le parsing dans
`analyze_batch()` :

```json
[
  {
    "id": "uid_md5",
    "relevance": 8,
    "summary_fr": "Résumé en 2-3 phrases.",
    "poc_idea": "Idée de POC en 1 phrase, ou chaîne vide.",
    "tags": ["dbt", "python"],
    "why_relevant": "Pourquoi utile en 1 phrase."
  }
]
```

**Règle** : modifier le schéma JSON implique de mettre à jour simultanément
`_build_prompt()`, le parsing dans `analyze_batch()`, `ScoredItem`, et
`bin/briefing.py`.

---

### `bin/briefing.py` — Génération des livrables

- `generate_html_briefing(scored_items, config) -> str` : HTML autonome (CSS
  intégré, **pas de CDN** — obligatoire pour email et usage hors ligne)
- `generate_markdown_briefing(scored_items, config) -> str` : compatible
  Obsidian / Notion, nommage `YYYY-WNN`

---

### `bin/mailer.py` — Envoi Gmail

- `send_email(html_body, to, subject)` : SMTP Gmail avec STARTTLS
- Lit `GMAIL_FROM` et `GMAIL_APP_PASSWORD` depuis l'environnement
- Hôte fixe : `smtp.gmail.com:587`

**Prérequis Gmail** :
1. Activer la validation en 2 étapes sur le compte Google
2. Générer un mot de passe d'application sur
   `https://myaccount.google.com/apppasswords`
3. Renseigner les 16 caractères dans `GMAIL_APP_PASSWORD` (sans espaces)

---

### `tasks.py` — Automatisation invoke

| Commande       | Action                                          |
|----------------|-------------------------------------------------|
| `inv lint`     | `ruff check` + `ruff format --check` + `mypy`  |
| `inv format`   | `ruff format` (correction en place)             |
| `inv test`     | `pytest` (doctest + unitaires + coverage)       |
| `inv check`    | `lint` puis `test` (CI complète)                |
| `inv run`      | `python -m veille_agent`                        |
| `inv dry-run`  | `python -m veille_agent --dry-run`              |

---

## Variables d'environnement

Copier `.env.example` en `.env` à la racine du projet.
`load_dotenv()` dans `__main__.py` les charge automatiquement au démarrage.

| Variable            | Obligatoire | Usage                                         |
|---------------------|-------------|-----------------------------------------------|
| `ANTHROPIC_API_KEY` | Oui         | Authentification API Claude                   |
| `GMAIL_FROM`        | Non         | Adresse Gmail expéditrice                     |
| `GMAIL_APP_PASSWORD`| Non         | Mot de passe d'application Gmail (16 chars)   |
| `GITHUB_TOKEN`      | Non         | API GitHub > 60 req/h (utile si > 10 topics)  |

**Règle** : ne jamais hard-coder de valeurs secrètes. `.env` est gitignore.

---

## Conventions de code

- Python 3.13, type hints complets sur toutes les fonctions publiques
- `beartype` pour la validation des types à l'exécution
- Docstrings Google style avec section `Examples:` (exécutées par pytest
  `--doctest-modules`)
- Formatage : `ruff format` (88 chars, double quotes)
- Lint : `ruff check` (E, W, F, I, B, C4, UP) — **zéro erreur exigée**
- Types : `mypy --strict` — **zéro erreur exigée**
- `# type: ignore[union-attr]` uniquement pour `response.content[0].text`
  (limitation du typage du SDK Anthropic)
- Logging via `logging.*` dans les modules, `print()` uniquement dans
  `__main__.py` pour les messages CLI utilisateur
- Les collecteurs et `fetch_fulltext` ne propagent jamais d'exception
- Les erreurs Claude API sont propagées (critiques)

---

## Commandes courantes

```bash
# Installation initiale
uv sync --extra dev --extra lint

# Copier et remplir les variables d'environnement
cp .env.example .env

# Vérification qualité complète
inv lint

# Tests
inv test

# Dry-run (sans Claude ni SQLite)
inv dry-run

# Exécution complète
inv run

# Avec envoi email
inv run --email vous@gmail.com

# Vider le cache SQLite (forcer une re-analyse complète)
python -c "import sqlite3; sqlite3.connect('src/veille_agent/data/watch.db').execute('DELETE FROM seen').connection.commit()"
```

---

## Points d'extension prioritaires

1. **Nouvelle source** : `collect_xxx() -> list[RawItem]` dans `collector.py`,
   appel dans `__main__.py::run()`. Aucun autre fichier à modifier.

2. **Modifier le profil** : éditer uniquement `config/profile.yaml` — pas de
   code à changer.

3. **Nouveau champ `ScoredItem`** : mettre à jour simultanément `_build_prompt()`
   + parsing dans `analyst.py`, `ScoredItem`, et `briefing.py`.

4. **Nouveau paramètre technique** : l'ajouter dans `WatchConfig`, l'utiliser
   via `config.xxx`.

5. **Boucle de feedback** : ajouter `useful INTEGER DEFAULT NULL` dans la
   table `seen`, implémenter `inv feedback` dans `tasks.py`.

---

## Infrastructure Docker et planification

### Fichiers Docker

- `Dockerfile` : image Python 3.13-slim multi-arch (linux/amd64 + linux/arm64).
  Build via `docker buildx` — compatible Raspberry Pi sans émulation à l'exécution.
- `docker-compose.yml` : définit le service `veille_agent` avec les volumes de
  persistance et la limite mémoire (256 Mo, adapté au Pi).
- `.dockerignore` : exclut `.env`, `data/`, `.venv/`, `tests/` du contexte de build.

### Volumes persistants sur le Raspberry Pi

Le conteneur est éphémère (`restart: no`) — les données survivent via des
bind-mounts dans `~/veille_agent/` sur le Pi :

```
~/veille_agent/
├── .env                    # secrets (ANTHROPIC_API_KEY, GMAIL_*)
├── docker-compose.yml      # copie ou symlink depuis le repo
├── config/
│   └── profile.yaml        # monté en :ro — éditer ici sans rebuild
└── data/
    ├── watch.db            # déduplication SQLite
    ├── briefings/          # HTML + Markdown générés
    └── log/                # app.log
```

### Workflow `weekly-watch.yml`

Déclenché chaque lundi à 6h UTC (7h/8h heure française selon DST) :

1. **Build** : `docker buildx build --platform linux/amd64,linux/arm64` et push
   sur `ghcr.io/<owner>/veille_agent:latest`
2. **Deploy** : SSH sur le Raspberry Pi via `appleboy/ssh-action`, `docker pull`
   puis `docker compose run --rm veille_agent`

### Secrets GitHub à configurer

Dans **Settings > Secrets and variables > Actions** du dépôt :

| Secret            | Valeur                                              |
|-------------------|-----------------------------------------------------|
| `RASPI_HOST`      | IP ou nom DNS du Raspberry Pi                       |
| `RASPI_USER`      | Utilisateur SSH (ex : `pi` ou `matthieu`)           |
| `RASPI_SSH_KEY`   | Clef privée SSH (contenu de `~/.ssh/id_ed25519`)    |
| `RASPI_PORT`      | Port SSH (défaut : `22`)                            |

`GITHUB_TOKEN` est fourni automatiquement par GitHub Actions.

### Mise en place initiale sur le Raspberry Pi

```bash
# 1. Créer la structure de dossiers
mkdir -p ~/veille_agent/data/briefings ~/veille_agent/data/log ~/veille_agent/config

# 2. Copier profile.yaml (ou le modifier directement)
cp /chemin/vers/repo/src/veille_agent/config/profile.yaml ~/veille_agent/config/

# 3. Créer le .env avec les secrets
nano ~/veille_agent/.env
# ANTHROPIC_API_KEY=sk-ant-...
# GMAIL_FROM=vous@gmail.com
# GMAIL_APP_PASSWORD=xxxxxxxxxxxxxxxx

# 4. Copier docker-compose.yml
cp /chemin/vers/repo/docker-compose.yml ~/veille_agent/

# 5. S'authentifier sur ghcr.io (une seule fois)
echo $GITHUB_TOKEN | docker login ghcr.io -u <votre-login-github> --password-stdin

# 6. Test manuel
cd ~/veille_agent
docker compose run --rm veille_agent
```

### Générer la clef SSH pour GitHub Actions

```bash
# Sur le Raspberry Pi
ssh-keygen -t ed25519 -C "github-actions-veille" -f ~/.ssh/github_actions
cat ~/.ssh/github_actions.pub >> ~/.ssh/authorized_keys

# Copier la clé privée dans le secret GitHub RASPI_SSH_KEY
cat ~/.ssh/github_actions
```

### Déclencher manuellement depuis Portainer

Dans Portainer, créer un **Stack** pointant vers `~/veille_agent/docker-compose.yml`.
Pour une exécution manuelle : **Stacks > veille_agent > Editor > Deploy the stack**,
ou via le bouton **Recreate** qui repart de l'image `latest`.

---

## Contraintes non négociables

- `.env` et `watch.db` ne sont jamais commités
- `inv lint` doit retourner **zéro erreur** — aucun `noqa` sans justification
- Batch size ≤ `config.claude_batch_size` (défaut 20) par appel Claude
- Le HTML généré est autonome (CSS intégré, pas de CDN externe)
- `profile.yaml` est la seule interface de personnalisation utilisateur —
  ne pas réintroduire de chaînes de contexte en dur dans le code Python
- Toute nouvelle fonction publique a une docstring avec `Examples:` testable

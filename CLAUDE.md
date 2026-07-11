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
**Modèle Claude** : défini dans `.env` (`CLAUDE_MODEL_BATCH`,
`CLAUDE_MODEL_DEEPDIVE`) — voir « Principe de configuration » ci-dessous
**Infrastructure** : Docker multi-arch (amd64 + arm64), Raspberry Pi, Portainer
**Registry** : GitHub Container Registry (`ghcr.io`)
**Planification** : GitHub Actions cron (lundi 6h UTC) → SSH → Raspberry Pi

---

## Principe de configuration

- `.env` : secrets/identifiants (`ANTHROPIC_API_KEY`, `GMAIL_APP_PASSWORD`,
  `GITHUB_TOKEN`, `YOUTUBE_API_KEY`) **et** paramètres techniques d'exécution
  non-fonctionnels — tout ce qui définit COMMENT/AVEC QUOI le programme
  tourne pour un déploiement donné (destinataire email `GMAIL_TO`, modèles
  Claude `CLAUDE_MODEL_BATCH`/`CLAUDE_MODEL_DEEPDIVE`).
- `profile.yaml` : personnalisation fonctionnelle — tout ce qui définit CE
  QUE le programme surveille et comment il juge la pertinence (thématiques,
  sources à surveiller, contexte narratif, critères et seuil de scoring).

**Aucune modification de fichier Python ne doit jamais être nécessaire pour
changer une thématique, une source, un seuil, une limite ou le modèle Claude
utilisé.**

Les constantes qui relèvent d'un détail d'implémentation restent légitimement
dans le code : timeouts réseau, noms de tables SQL, formats de date, CSS du
HTML généré, logique de retry. La frontière : si la valeur encode « qui je
suis / ce qui m'intéresse / comment le pipeline doit se comporter », elle va
dans `profile.yaml` ; si elle encode « comment le code accomplit
techniquement la tâche », elle reste en dur.

**Modèle Claude — deux variables, alignées sur la nature de la tâche** :

- `CLAUDE_MODEL_BATCH` (utilisé par `analyze_batch()`) : scoring/tagging
  structuré sur le volume principal d'articles. Tâche de classification
  où Haiku 4.5 est explicitement recommandé par Anthropic (rapport
  qualité/coût 3x meilleur que Sonnet pour ce type d'usage) →
  `claude-haiku-4-5`.
- `CLAUDE_MODEL_DEEPDIVE` (utilisé par `deepdive()`/`run_deepdives()` **et**
  `generate_monthly_recap()`) : recherche web + synthèse sur un volume
  faible (articles score >= 9, recap mensuel) — même nature de tâche
  agentique pour les deux, donc pas de troisième variable
  `CLAUDE_MODEL_RECAP`. Sonnet 5 apporte un gain de qualité réel sur ce
  type de synthèse, et le volume d'appels reste assez faible pour que le
  coût plus élevé soit marginal → `claude-sonnet-5`.

Les deux sont lues directement depuis l'environnement (pas de valeur par
défaut cachée — erreur explicite si absente). Vérifier
https://platform.claude.com/docs/en/about-claude/model-deprecations avant
toute mise à jour.

**Notes sur Sonnet 5** (pertinentes si `CLAUDE_MODEL_DEEPDIVE` est concerné) :

- Tokenizer : ~30 % de tokens en plus à texte égal par rapport à
  Sonnet 4.6/Haiku 4.5 — à revoir si le budget de tokens des deepdives
  devient serré.
- Garde-fous cybersécurité : peut refuser certains contenus dual-use.
  Pertinent car la source explain-openclaw couvre des audits de sécurité —
  surveiller les logs si des deepdives échouent silencieusement sur ce
  type de contenu.

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
│       │   ├── profile.py             # UserProfile (profil + technique) + load_profile()
│       │   ├── collector.py           # collecte RSS / arXiv / GitHub
│       │   ├── filter.py              # pré-filtrage par mots-clés
│       │   ├── reader.py              # extraction full-text via Jina Reader
│       │   ├── youtube.py             # collecte + transcript YouTube
│       │   ├── analyst.py             # analyse batch + deepdive via Claude API
│       │   ├── briefing.py            # génération HTML + Markdown
│       │   ├── recap.py               # recap mensuel Top-K + persistance SQLite
│       │   ├── mailer.py              # envoi Gmail SMTP
│       │   └── publisher.py           # copie du briefing vers un vault (Obsidian…)
│       ├── config/                    # dossier runtime (gitignore sauf profile.yaml)
│       │   └── profile.yaml           # ÉDITER ICI — profil utilisateur déclaratif
│       ├── data/                      # dossier runtime (gitignore)
│       │   ├── watch.db               # SQLite déduplication + recap
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
- `scoring.threshold` : seuil unique d'inclusion dans le briefing et de
  persistance recap (défaut 6.0) — source de vérité unique, utilisée partout
  dans le pipeline
- `rss_feeds` : sources RSS/Atom (`name` + `url`)
- `rss_since_days` : fenêtre de collecte RSS/Atom en jours
- `arxiv_categories` : catégories arXiv surveillées
- `github_topics` : topics GitHub Trending surveillés
- `youtube_channels` : chaînes YouTube (handles `@...` ou identifiants `UC...`)
- `youtube_max_per_channel` : nombre max de vidéos collectées par chaîne
- `claude_batch_size` : nombre d'articles par appel Claude
- `deepdive_threshold` : score minimum déclenchant un deepdive
- `max_items_per_briefing` : nombre maximum d'articles dans un briefing
- `recap_since_weeks` : fenêtre par défaut du recap mensuel, en semaines

**Règle** : tout ce qui est modifiable sans redéploiement va dans
`profile.yaml`. Voir « Principe de configuration » ci-dessus.

---

## Architecture des modules

### `__main__.py` — Orchestrateur + CLI

Point d'entrée unique. Charge `.env` via `load_dotenv()` au démarrage.

Fonctions :
- `_get_package_dir(folder_name)` : résout les chemins runtime via
  `importlib.resources`
- `_setup_logging(log_path)` : configure le logger dans `log/app.log`
- `run(profile, db_path, output_dir, email_to, dry_run)` : pipeline
  complet, retourne la liste des `ScoredItem`
- `main()` : parse les arguments CLI, charge `UserProfile`, appelle `run()`

**Arguments CLI** :
```
--email ADRESSE     Envoyer le briefing par email via Gmail
--publish-path CHEMIN  Copier le briefing markdown vers ce répertoire en plus
                    de output_dir (ex : vault Obsidian). Défaut : PUBLISH_PATH
--dry-run           Collecter et filtrer sans appeler Claude ni écrire en base
--output-dir PATH   Dossier de sortie (défaut : data/briefings/)
--no-youtube        Désactiver la collecte YouTube
--no-deepdive       Désactiver le deepdive automatique
--recap             Générer le recap mensuel Top-K (sans run hebdomadaire)
--recap-weeks N     Fenêtre du recap en semaines (défaut : profile.recap_since_weeks)
```

**Règle** : `__main__.py` n'orchestre que — toute logique métier va dans `bin/`.

---

### `bin/profile.py` — `UserProfile` + `load_profile()`

`UserProfile` est la dataclass unique portant tout ce qui est personnalisable :
thématiques, contexte narratif, critères de scoring, sources à surveiller et
paramètres techniques (seuils, tailles de batch).

- `UserProfile` : `topics`, `context`, `scoring_high/medium/low`, `threshold`,
  `rss_feeds`, `rss_since_days`, `arxiv_categories`, `github_topics`,
  `youtube_channels`, `youtube_max_per_channel`,
  `claude_batch_size`, `deepdive_threshold`, `max_items_per_briefing`,
  `recap_since_weeks`
- `load_profile(path: Path) -> UserProfile` : charge `profile.yaml` via
  `yaml.safe_load()`, accès direct `data["clé"]` (pas de fallback silencieux)

**Règle** : modifier `profile.yaml` ne nécessite jamais de toucher au code
Python.

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
`collector.py`, l'appeler dans `__main__.py::run()`. Si la source est
paramétrable (URL, catégories, topics…), ajouter le champ correspondant dans
`UserProfile` et `profile.yaml` — aucun autre fichier à modifier.

---

### `bin/filter.py` — Pré-filtrage

- `keyword_score(item, topics) -> float` : regex `\bword\b` sur titre + résumé
- `pre_filter(items, topics, threshold=0.08)` : élimine le bruit avant Claude

Seuil intentionnellement bas (0.08) — Claude affine ensuite. Ce seuil est un
détail de calibration interne au filtre (couplé à la formule
`hits / max(len(topics)*0.3, 1)`), pas une préférence utilisateur : il reste
en dur.

---

### `bin/reader.py` — Extraction full-text

- `fetch_fulltext(url, max_chars=3000) -> str`
- Préfixe `https://r.jina.ai/` — API publique, sans clé, ~60 req/min
- Appelé uniquement si `len(item.summary) < 100`
- Retourne `""` en cas d'erreur (dégradation gracieuse)

---

### `bin/youtube.py` — Collecte YouTube

- `collect_youtube(channels, since_days, max_per_channel) -> list[RawItem]`
- `fetch_transcript(video_id, max_chars=2000) -> str`
- Nécessite `YOUTUBE_API_KEY` dans `.env`

---

### `bin/analyst.py` — Cœur IA

- `analyze_batch(items, profile, fulltext, model=None) -> list[ScoredItem]`
  — `model` résolu par l'appelant depuis `CLAUDE_MODEL_BATCH` (`.env`)
- `deepdive(item, profile, model=None) -> str` — approfondissement via l'outil
  `web_search` intégré, pour les articles `relevance >= 9`, `model` résolu
  depuis `CLAUDE_MODEL_DEEPDIVE` (`.env`)
- `run_deepdives(scored_items, profile, model=None, threshold=9.0) -> list[ScoredItem]`
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

- `generate_html_briefing(scored_items, profile) -> str` : HTML autonome (CSS
  intégré, **pas de CDN** — obligatoire pour email et usage hors ligne)
- `generate_markdown_briefing(scored_items, profile) -> str` : compatible
  Obsidian / Notion, nommage `YYYY-WNN`

Les deux fonctions utilisent `profile.threshold` (filtrage) et
`profile.max_items_per_briefing` (plafond). Les seuils de classe CSS
(`score.top` ≥ 9, `score.high` ≥ 8) sont un détail d'affichage HTML et
restent en dur.

---

### `bin/recap.py` — Recap mensuel

- `persist_scored_items(scored_items, stem, db_path, threshold) -> None` :
  enregistre les articles avec `relevance >= threshold` dans la table
  `briefing_items`
- `generate_monthly_recap(db_path, profile, output_dir, since_weeks, email_to)` :
  Top-K du mois via `CLAUDE_MODEL_DEEPDIVE` (`.env`) — même variable que le
  deepdive, tâche de synthèse de même nature

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

### `bin/publisher.py` — Publication vers un répertoire secondaire

- `publish_briefing(md_path, publish_path)` : copie (`shutil.copy2`) le
  briefing markdown déjà écrit dans `output_dir` vers `publish_path` (ex :
  point de montage local vers un vault Obsidian synchronisé)
- Échec non-bloquant : `OSError` capturée et loggée en warning — l'email et
  `output_dir` restent le canal principal, cette copie ne doit jamais faire
  échouer le run
- Piloté par `--publish-path` (CLI) ou `PUBLISH_PATH` (`.env`) — même nature
  de paramètre que `--email`/`GMAIL_TO` : configuration d'exécution, pas de
  personnalisation de contenu

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
| `inv recap`    | `python -m veille_agent --recap`                |

---

## Variables d'environnement

Copier `.env.example` en `.env` à la racine du projet.
`load_dotenv()` dans `__main__.py` les charge automatiquement au démarrage.

| Variable            | Obligatoire | Usage                                                             |
|---------------------|-------------|--------------------------------------------------------------------|
| `ANTHROPIC_API_KEY` | Oui         | Authentification API Claude                                       |
| `CLAUDE_MODEL_BATCH`| Oui         | Modèle Claude pour le scoring/tagging en masse (`analyze_batch`)   |
| `CLAUDE_MODEL_DEEPDIVE`| Oui      | Modèle Claude pour les deepdives et le recap mensuel               |
| `GMAIL_FROM`        | Non         | Adresse Gmail expéditrice                                          |
| `GMAIL_APP_PASSWORD`| Non         | Mot de passe d'application Gmail (16 chars)                        |
| `GITHUB_TOKEN`      | Non         | API GitHub > 60 req/h (utile si > 10 topics)                       |
| `YOUTUBE_API_KEY`   | Non         | Requis pour activer la collecte YouTube                            |
| `PUBLISH_PATH`      | Non         | Répertoire secondaire de copie du briefing (ex : vault Obsidian)   |

**Règle** : `.env` est réservé aux secrets/identifiants et aux paramètres
techniques d'exécution non-fonctionnels (modèle Claude, destinataire email) —
jamais de valeur de personnalisation fonctionnelle (thématique, source,
seuil de scoring), qui vit dans `profile.yaml`. `.env` est gitignore.

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
   appel dans `__main__.py::run()`. Si l'URL/les paramètres doivent être
   personnalisables, ajouter le champ dans `UserProfile` + `profile.yaml`.
   Aucun autre fichier à modifier.

2. **Modifier le profil** : éditer uniquement `config/profile.yaml` — pas de
   code à changer.

3. **Changer le modèle Claude** : éditer `CLAUDE_MODEL_BATCH` et/ou
   `CLAUDE_MODEL_DEEPDIVE` dans `.env` — pas de code à changer. Vérifier
   https://platform.claude.com/docs/en/about-claude/model-deprecations avant
   toute mise à jour.

4. **Nouveau champ `ScoredItem`** : mettre à jour simultanément `_build_prompt()`
   + parsing dans `analyst.py`, `ScoredItem`, et `briefing.py`.

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
| `RASPI_USER`      | Utilisateur SSH (ex : `pi` ou `matthieu`)           |
| `RASPI_SSH_KEY`   | Clef privée SSH (contenu de `~/.ssh/id_ed25519`)    |
| `RASPI_PORT`      | Port SSH (défaut : `22`)                            |

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
- Batch size ≤ `profile.claude_batch_size` (défaut 20) par appel Claude
- Le HTML généré est autonome (CSS intégré, pas de CDN externe)
- `profile.yaml` est la seule interface de personnalisation utilisateur —
  ne pas réintroduire de chaînes de contexte en dur dans le code Python
- Toute nouvelle fonction publique a une docstring avec `Examples:` testable

FROM python:3.13-slim

LABEL maintainer="matthieu.daviaud@gmail.com"
LABEL description="Agent de veille technologique hebdomadaire"

WORKDIR /app

RUN pip install --no-cache-dir uv

# Passe 1 — dépendances tierces uniquement.
# --no-install-project : n'installe pas veille_agent lui-même,
# donc hatchling ne cherche pas py.typed qui n'existe pas encore.
# Ce layer est mis en cache tant que pyproject.toml / uv.lock ne changent pas.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Passe 2 — code source puis installation du projet.
# uv sync est idempotent : seul le projet manquant est installé,
# les dépendances déjà présentes ne sont pas retéléchargées.
COPY src/ ./src/
RUN uv sync --no-dev --frozen

# Dossiers runtime (montés en volume en production)
RUN mkdir -p src/veille_agent/data/briefings \
             src/veille_agent/log \
             src/veille_agent/config

# Profil YAML par défaut (écrasé par le volume en production)
COPY src/veille_agent/config/profile.yaml ./src/veille_agent/config/profile.yaml

CMD ["uv", "run", "python", "-m", "veille_agent"]

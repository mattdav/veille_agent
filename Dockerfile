FROM python:3.13-slim

LABEL maintainer="matthieu.daviaud@gmail.com"
LABEL description="Agent de veille technologique hebdomadaire"

WORKDIR /app

RUN pip install --no-cache-dir uv

# Copier uniquement les fichiers de métadonnées en premier.
# uv résout et installe les dépendances tierces à cette étape,
# sans toucher au projet lui-même (--no-install-project).
# Cela préserve le cache Docker : ce layer ne se reconstruit que
# si pyproject.toml ou uv.lock changent, pas à chaque modif du code.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# Copier le code source (invalidera le cache Docker si le code change)
COPY src/ ./src/

# Installer le projet lui-même maintenant que src/ est présent.
# --no-deps : les dépendances sont déjà installées à l'étape précédente.
RUN uv sync --no-dev --frozen --no-deps

# Créer les dossiers runtime montés en volume en production
RUN mkdir -p src/veille_agent/data/briefings \
             src/veille_agent/log \
             src/veille_agent/config

# Profil YAML par défaut (écrasé par le volume en production)
COPY src/veille_agent/config/profile.yaml ./src/veille_agent/config/profile.yaml

CMD ["uv", "run", "python", "-m", "veille_agent"]

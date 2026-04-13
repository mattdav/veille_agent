# Image officielle Python multi-arch (compatible Raspberry Pi ARM64 et x86_64)
FROM python:3.13-slim

# Métadonnées
LABEL maintainer="matthieu.daviaud@gmail.com"
LABEL description="Agent de veille technologique hebdomadaire"

# Répertoire de travail dans le conteneur
WORKDIR /app

# Installer uv pour la gestion des dépendances
RUN pip install --no-cache-dir uv

# Copier les fichiers de dépendances en premier (layer cache Docker)
# uv.lock est versionné — présent dans le repo après retrait du .gitignore
COPY pyproject.toml uv.lock ./

# Installer uniquement les dépendances runtime (pas dev/lint/docs)
# --frozen : refuse d'installer si le lock est désynchronisé avec pyproject.toml
RUN uv sync --no-dev --frozen

# Copier le code source
COPY src/ ./src/

# Créer les dossiers runtime (data, log, config)
# Ces dossiers seront montés en volume pour la persistance
RUN mkdir -p src/veille_agent/data/briefings \
             src/veille_agent/log \
             src/veille_agent/config

# Copier le profil YAML par défaut (écrasé par le volume en production)
COPY src/veille_agent/config/profile.yaml ./src/veille_agent/config/profile.yaml

# Commande par défaut : exécution de l'agent
CMD ["uv", "run", "python", "-m", "veille_agent"]

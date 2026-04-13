#!/bin/bash
# /home/pi/veille_agent/run.sh
# Lancé par cron chaque lundi matin.
# Pull la dernière image et exécute l'agent une fois.

set -e

WORKDIR="$(dirname "$0")"
OWNER="VOTRE_LOGIN_GITHUB"    # ← à remplacer
IMAGE="ghcr.io/${OWNER}/veille_agent:latest"

echo "[$(date)] Démarrage veille_agent..."

cd "$WORKDIR"

# Pull silencieux (pas d'output si l'image est déjà à jour)
docker pull "$IMAGE" --quiet

# Lancer le conteneur avec les volumes et le .env
# --rm : supprime le conteneur après exécution (pas de résidu dans Portainer)
docker run --rm \
    --name veille_agent_run \
    --env-file .env \
    --memory 256m \
    -v "$WORKDIR/data/briefings:/app/src/veille_agent/data/briefings" \
    -v "$WORKDIR/data/log:/app/src/veille_agent/log" \
    -v "$WORKDIR/data:/app/src/veille_agent/data" \
    -v "$WORKDIR/config/profile.yaml:/app/src/veille_agent/config/profile.yaml:ro" \
    "$IMAGE"

echo "[$(date)] veille_agent terminé."

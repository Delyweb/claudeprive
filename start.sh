#!/bin/bash
# Nettoyage des caches Python pour éviter les conflits de version
find . -type d -name "__pycache__" -exec rm -rf {} +

echo "Starting ClaudePrivé..."
# --preload permet de charger l'application avant de forker les workers
# Cela permet de voir les erreurs de démarrage immédiatement dans les logs
exec gunicorn --bind 0.0.0.0:8009 --workers 2 --threads 8 --timeout 600 --preload --access-logfile - --log-level info app:app

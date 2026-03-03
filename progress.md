# Progress: ClaudePrivé

## Statut Global
Le projet est terminé et fonctionnel. Toutes les fonctionnalités principales (Chat, Upload, Projets, Coûts) sont implémentées.

## Fonctionnalités (Roadmap)

- [x] **Backend Flask**
    - [x] Routes API RESTful
    - [x] Serveur Gunicorn
    - [x] Persistance JSON
- [x] **Intégration AWS Bedrock**
    - [x] Support Claude 3.5 Sonnet
    - [x] Support Claude 3 Haiku
    - [x] Gestion des coûts (Input/Output tokens)
- [x] **Frontend SPA**
    - [x] Chat interface
    - [x] Historique des conversations
    - [x] Indicateur de frappe
    - [x] Rendu Markdown
- [x] **Gestion de Fichiers**
    - [x] Upload PDF, DOCX, TXT
    - [x] Extraction de texte
    - [x] Association aux Projets
- [x] **Fonctionnalités Avancées**
    - [x] Gestion de "Projets"
    - [x] Prompts système personnalisables
    - [x] Configuration utilisateur (région, modèle)
- [x] **Déploiement**
    - [x] Dockerfile optimisé
    - [x] docker-compose.yml
    - [x] Documentation Memory Bank

## Problèmes Connus
-   Aucun bug majeur connu pour le moment.
-   L'erreur de `ValidationException` sur Bedrock a été corrigée le 03/03/2026.

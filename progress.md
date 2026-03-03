# Progress: ClaudePrivé

## Statut Global
Le projet est stable (v2.3). La fonctionnalité de Journal Quotidien a été temporairement retirée pour des raisons de stabilité serveur.

## Fonctionnalités (Roadmap)

- [x] **Backend Flask**
    - [x] Routes API RESTful
    - [x] Serveur Gunicorn
    - [x] Persistance JSON
    - [x] Gestion intelligente des régions (US/EU)
    - [x] Route de déplacement de conversation (PUT /project)
    - [x] Route de recherche (GET /search)
    - [x] Intégration S3 / Pegasus (Vidéo)
    - [ ] **Scheduler (Suspendu pour cause de crash 502)**
- [x] **Intégration AWS Bedrock**
    - [x] Support Modèles 2026 (Opus 4.6, Sonnet 4.5, Haiku 4.5)
    - [x] Profils Cross-Region Europe/US
    - [x] Gestion des coûts
    - [x] Twelve Labs Pegasus (Video-to-Text)
- [x] **Frontend SPA**
    - [x] Chat interface moderne
    - [x] Historique des conversations
    - [x] Indicateur de frappe
    - [x] Drag & Drop pour classer les conversations
    - [x] Menu Contextuel (Renommer/Déplacer/Supprimer)
    - [x] Barre de Recherche (Historique global)
    - [ ] Bouton "Journal" (Désactivé)
- [x] **Confidentialité**
    - [x] Prompt système "Europe" par défaut
    - [x] Limitation aux régions EU dans l'interface
- [x] **Gestion de Fichiers**
    - [x] Upload PDF, DOCX, TXT
    - [x] Upload Vidéo (MP4, MOV...)
    - [x] Extraction de texte & Stockage complet (RAG)
    - [x] Association aux Projets
- [x] **Fonctionnalités Avancées**
    - [x] Gestion de "Projets"
    - [x] Prompts système personnalisables (dont Domotique)
- [x] **Déploiement**
    - [x] Dockerfile optimisé
    - [x] docker-compose.yml
    - [x] Documentation Memory Bank complète
    - [x] Guide S3

## Problèmes Connus
-   Le module `APScheduler` cause des erreurs 502 avec Gunicorn sur certains environnements. Il a été retiré.

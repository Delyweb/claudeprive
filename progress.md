# Progress: ClaudePrivé

## Statut Global
Le projet est en version v2.3. Les fonctionnalités de **Journal Quotidien** ont été retirées pour garantir la stabilité. Les autres fonctionnalités (Recherche, Vidéo, RAG) sont opérationnelles.

## Fonctionnalités (Roadmap)

- [x] **Backend Flask**
    - [x] Routes API RESTful
    - [x] Serveur Gunicorn
    - [x] Persistance JSON
    - [x] Gestion intelligente des régions (US/EU)
    - [x] Route de déplacement de conversation (PUT /project)
    - [x] Route de recherche (GET /search)
    - [x] Intégration S3 / Pegasus (Vidéo)
    - [ ] ~~Scheduler (APScheduler) pour Journal Quotidien~~ (Retiré)
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
    - [ ] ~~Bouton "Journal" dans les projets~~ (Retiré)
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
    - [x] Prompts système personnalisables
    - [ ] ~~Génération automatique de journal (Actions/Décisions)~~ (Retiré)
- [x] **Déploiement**
    - [x] Dockerfile optimisé
    - [x] docker-compose.yml
    - [x] Documentation Memory Bank complète
    - [x] Guide S3

## Problèmes Connus
-   L'analyse vidéo complète nécessite une configuration S3 manuelle.
-   La fonctionnalité Journal a été instable et est désactivée.

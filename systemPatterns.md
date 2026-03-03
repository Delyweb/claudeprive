# System Patterns: ClaudePrivé

## Architecture Technique
L'application suit une architecture monolithique simple mais efficace, optimisée pour un déploiement facile via Docker.

### 1. Backend (Flask)
-   **Langage** : Python 3.12.
-   **Framework** : Flask (léger, routes API RESTful).
-   **Serveur WSGI** : Gunicorn (pour la production avec workers/threads).
-   **Services** :
    -   `api/chat` : Gère la logique de conversation et les appels Bedrock.
    -   `api/upload` : Gère l'upload et l'extraction de texte (PyPDF2, python-docx).
    -   `api/projects` : CRUD pour les projets.
    -   `api/costs` : Calcul et persistance des coûts.

### 2. Frontend (SPA Vanilla)
-   **Technologie** : HTML5 + CSS3 + JavaScript (ES6+).
-   **Approche** : Single Page Application (SPA) contenue dans un seul fichier `index.html` servi par Flask.
-   **Communication** : Appels `fetch` vers l'API backend.
-   **État** : État local en mémoire JS (conversations, messages, settings), rechargé depuis l'API.

### 3. Persistance (JSON)
-   **Stockage** : Fichiers JSON plats stockés dans un volume Docker monté (`/app/data`).
-   **Fichiers** :
    -   `conversations.json` : Historique complet des chats.
    -   `projects.json` : Métadonnées des projets et liens vers les fichiers.
    -   `costs.json` : Registre quotidien des tokens consommés.
    -   `prompts.json` : Bibliothèque de prompts système.
    -   `settings.json` : Configuration utilisateur (modèle, région).
-   **Avantage** : Sauvegarde facile, pas de base de données à administrer, lisible par l'humain.

### 4. Intégration IA (AWS Bedrock)
-   **Client** : `boto3` (AWS SDK for Python).
-   **Modèles** : Claude 3.5 Sonnet et Claude 3 Haiku via l'API `invoke_model`.
-   **Authentification** : Utilise les crédentials AWS de l'environnement (variables d'env ou profil AWS CLI).

## Patterns de Code
-   **Routes API** : Préfixées par `/api/`.
-   **Gestion des Erreurs** : Renvoient des JSON `{"error": "message"}` avec codes HTTP appropriés.
-   **Extraction de Texte** : Fonction utilitaire `extract_text_from_file` qui gère plusieurs formats selon l'extension.
-   **Calcul de Coût** : Effectué côté serveur après chaque appel Bedrock et ajouté à l'historique global + retourné au client.
